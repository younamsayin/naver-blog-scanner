#!/usr/bin/env python3
"""
Naver Blog Scanner
──────────────────
Scans Naver blogs listed in blogs.txt for new posts,
summarizes each post with Gemini, saves them locally,
and sends the summary to Telegram.

Usage:
  python3 main.py              # normal run (new posts only)
  python3 main.py --backfill   # also summarize all already-existing posts
"""

import os
import sys
import re
import json
import time
import logging
import argparse
from datetime import datetime
from pathlib import Path

import requests
import feedparser
from bs4 import BeautifulSoup
import google.generativeai as genai
from dotenv import load_dotenv

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent
CONFIG_FILE  = BASE_DIR / "config.env"
BLOGS_FILE   = BASE_DIR / "blogs.txt"
STATE_FILE   = BASE_DIR / "state.json"
SUMMARIES_DIR= BASE_DIR / "summaries"
PROMPT_FILE  = BASE_DIR / "prompt.md"
LOG_FILE     = BASE_DIR / "scanner.log"

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ─── Mobile browser header ────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    )
}


# ══════════════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════════════

def load_config() -> dict:
    load_dotenv(CONFIG_FILE)
    cfg = {
        "gemini_key": os.getenv("GEMINI_API_KEY", ""),
        "tg_token":   os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "tg_chat":    os.getenv("TELEGRAM_CHAT_ID", ""),
    }
    missing = [k for k, v in cfg.items() if not v or v.startswith("your_")]
    if missing:
        log.error(
            "The following config keys are not set in config.env: %s\n"
            "Please fill in config.env and try again.",
            missing,
        )
        sys.exit(1)
    return cfg


# ══════════════════════════════════════════════════════════════════════════════
# State  (tracks which post IDs have already been processed)
# ══════════════════════════════════════════════════════════════════════════════

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict):
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Blog list
# ══════════════════════════════════════════════════════════════════════════════

def load_blogs() -> list:
    if not BLOGS_FILE.exists():
        log.error("blogs.txt not found at %s", BLOGS_FILE)
        return []
    lines = BLOGS_FILE.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


def extract_blog_id(url: str) -> str:
    """Pull the blog ID out of any Naver blog URL."""
    m = re.search(r"blog\.naver\.com/([^/?#\s]+)", url)
    return m.group(1) if m else ""


# ══════════════════════════════════════════════════════════════════════════════
# RSS
# ══════════════════════════════════════════════════════════════════════════════

def get_rss_entries(blog_id: str) -> list:
    rss_url = f"https://rss.blog.naver.com/{blog_id}"
    try:
        feed = feedparser.parse(rss_url)
        return feed.entries
    except Exception as exc:
        log.error("[%s] RSS fetch failed: %s", blog_id, exc)
        return []


# ══════════════════════════════════════════════════════════════════════════════
# Content scraping (mobile Naver)
# ══════════════════════════════════════════════════════════════════════════════

def get_post_content(post_url: str) -> str:
    """
    Fetch the full text of a Naver blog post.
    Tries the mobile URL first (easier to parse), falls back to desktop.
    """
    try:
        # Build mobile URL
        m = re.search(r"blog\.naver\.com/([^/]+)/(\d+)", post_url)
        if m:
            mobile_url = f"https://m.blog.naver.com/{m.group(1)}/{m.group(2)}"
        else:
            mobile_url = post_url.replace("blog.naver.com", "m.blog.naver.com")

        resp = requests.get(mobile_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Try known content container selectors (Naver uses several editor versions)
        candidates = [
            soup.find("div", class_="se-main-container"),
            soup.find("div", class_="post_ct"),
            soup.find("div", id="postViewArea"),
            soup.find("div", class_="se_component_wrap"),
            soup.find("div", class_="blog_content"),
            soup.find("div", class_="__se_component_area"),
        ]

        for el in candidates:
            if el:
                for junk in el.find_all(["script", "style", "iframe", "button"]):
                    junk.decompose()
                text = el.get_text(separator="\n", strip=True)
                if len(text) > 150:      # ignore tiny/empty containers
                    return text

        # Last-resort: strip the whole body
        body = soup.find("body")
        if body:
            for junk in body.find_all(["script", "style", "nav", "header", "footer"]):
                junk.decompose()
            return body.get_text(separator="\n", strip=True)[:10_000]

    except Exception as exc:
        log.error("Content fetch failed for %s: %s", post_url, exc)

    return ""


# ══════════════════════════════════════════════════════════════════════════════
# Gemini summarization
# ══════════════════════════════════════════════════════════════════════════════

def summarize(
    content: str,
    title: str,
    blog_id: str,
    prompt_template: str,
    gemini_key: str,
) -> str:
    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    full_prompt = (
        f"{prompt_template}\n\n"
        f"[Source Data]\n"
        f"Blog: {blog_id}\n"
        f"Title: {title}\n\n"
        f"Content:\n{content[:12_000]}"      # cap to avoid token limits
    )

    try:
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as exc:
        log.error("Gemini summarization failed: %s", exc)
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# Telegram
# ══════════════════════════════════════════════════════════════════════════════

MAX_TG_CHARS = 4000   # Telegram hard limit is 4096; leave some headroom


def send_telegram(text: str, token: str, chat_id: str):
    """Send a message to Telegram, splitting into chunks if it's too long."""
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = [text[i : i + MAX_TG_CHARS] for i in range(0, len(text), MAX_TG_CHARS)]

    for chunk in chunks:
        sent = False
        # Try Markdown first, fall back to plain text
        for parse_mode in ("Markdown", None):
            payload: dict = {"chat_id": chat_id, "text": chunk}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            try:
                r = requests.post(api_url, json=payload, timeout=15)
                r.raise_for_status()
                sent = True
                break
            except Exception as exc:
                if parse_mode:
                    log.warning("Telegram Markdown send failed, retrying plain: %s", exc)
                else:
                    log.error("Telegram send failed: %s", exc)
        if sent:
            time.sleep(0.5)   # short pause between chunks


# ══════════════════════════════════════════════════════════════════════════════
# Local file saving
# ══════════════════════════════════════════════════════════════════════════════

def save_summary_file(
    blog_id: str,
    post_title: str,
    post_date: str,
    post_url: str,
    summary: str,
) -> Path:
    SUMMARIES_DIR.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filepath = SUMMARIES_DIR / f"{date_str}_{blog_id}.md"

    sep = "─" * 60
    entry = (
        f"\n{sep}\n"
        f"Blog   : {blog_id}\n"
        f"Title  : {post_title}\n"
        f"Date   : {post_date}\n"
        f"URL    : {post_url}\n"
        f"Scanned: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{sep}\n\n"
        f"{summary}\n"
    )
    with open(filepath, "a", encoding="utf-8") as fh:
        fh.write(entry)

    log.info("Summary saved → %s", filepath)
    return filepath


# ══════════════════════════════════════════════════════════════════════════════
# Main scan logic
# ══════════════════════════════════════════════════════════════════════════════

def scan(backfill: bool = False):
    log.info("=" * 60)
    log.info("Naver Blog Scanner — starting run")
    log.info("=" * 60)

    cfg             = load_config()
    state           = load_state()
    blogs           = load_blogs()
    prompt_template = PROMPT_FILE.read_text(encoding="utf-8")

    if not blogs:
        log.warning("No blog URLs found in blogs.txt — nothing to do.")
        return

    total_new = 0

    for blog_url in blogs:
        blog_id = extract_blog_id(blog_url)
        if not blog_id:
            log.warning("Cannot parse blog ID from URL: %s", blog_url)
            continue

        log.info("─── Scanning blog: %s", blog_id)
        entries = get_rss_entries(blog_id)

        if not entries:
            log.warning("[%s] No RSS entries returned.", blog_id)
            continue

        is_first_run = blog_id not in state
        seen: set = set(state.get(blog_id, []))

        # First run without --backfill → mark all existing posts as seen, skip.
        if is_first_run and not backfill:
            all_ids = [e.get("id", e.get("link", "")) for e in entries]
            log.info(
                "[%s] First run — marking %d existing posts as seen "
                "(use --backfill to summarize them too).",
                blog_id, len(all_ids),
            )
            state[blog_id] = all_ids
            save_state(state)
            continue

        for entry in entries:
            post_id    = entry.get("id", entry.get("link", ""))
            post_title = entry.get("title", "Untitled")
            post_link  = entry.get("link", "")
            post_date  = entry.get("published", str(datetime.now()))

            if post_id in seen:
                continue

            log.info("[%s] New post found → %s", blog_id, post_title)

            # ── Get content ──────────────────────────────────────────────────
            content = get_post_content(post_link)

            if not content:
                # Fall back to RSS description
                raw = entry.get("summary", entry.get("description", ""))
                content = BeautifulSoup(raw, "lxml").get_text(separator="\n", strip=True)

            if not content.strip():
                log.warning("[%s] Empty content — skipping: %s", blog_id, post_title)
                seen.add(post_id)
                state[blog_id] = list(seen)
                save_state(state)
                continue

            # ── Summarize ────────────────────────────────────────────────────
            summary = summarize(
                content, post_title, blog_id, prompt_template, cfg["gemini_key"]
            )
            if not summary:
                log.warning("[%s] Summarization returned empty result.", blog_id)
                continue

            # ── Save locally ─────────────────────────────────────────────────
            save_summary_file(blog_id, post_title, post_date, post_link, summary)

            # ── Send to Telegram ─────────────────────────────────────────────
            header = (
                f"📰 *New Post — {blog_id}*\n"
                f"*{post_title}*\n"
                f"🗓 {post_date}\n"
                f"🔗 {post_link}\n\n"
            )
            send_telegram(header + summary, cfg["tg_token"], cfg["tg_chat"])

            # ── Update state ─────────────────────────────────────────────────
            seen.add(post_id)
            state[blog_id] = list(seen)
            save_state(state)
            total_new += 1

            time.sleep(3)   # polite delay between posts

    log.info("Run complete. New posts processed: %d", total_new)


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Naver Blog Scanner")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help=(
            "On first run, summarize ALL existing posts. "
            "Default: mark them as seen and only summarize future new posts."
        ),
    )
    args = parser.parse_args()
    scan(backfill=args.backfill)

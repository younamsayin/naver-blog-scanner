#!/usr/bin/env python3
"""
Naver Blog Scanner
──────────────────
Scans Naver blogs listed in blogs.txt for new posts,
summarizes each post with Gemini, saves them locally,
and sends the summary to Telegram.

Usage:
  ./run.sh                             # scan once right now
  ./venv/bin/python3 main.py run       # scan once right now
  ./venv/bin/python3 main.py run --backfill
  ./venv/bin/python3 main.py test      # summarize one random post
  ./venv/bin/python3 main.py watch
  ./venv/bin/python3 main.py watch --interval 600
"""

import os
import sys
import re
import json
import time
import calendar
import logging
import argparse
import random
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

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

DEFAULT_MODEL = "gemini-2.0-flash"
DEFAULT_CONTENT_CHAR_LIMIT = 12000
DEFAULT_FIRST_RUN_LOOKBACK_DAYS = 3
DEFAULT_WATCH_INTERVAL_SECONDS = 900

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
        "llm_model":  os.getenv("LLM_MODEL", DEFAULT_MODEL),
        "content_char_limit": os.getenv("CONTENT_CHAR_LIMIT", str(DEFAULT_CONTENT_CHAR_LIMIT)),
        "first_run_lookback_days": os.getenv(
            "FIRST_RUN_LOOKBACK_DAYS",
            str(DEFAULT_FIRST_RUN_LOOKBACK_DAYS),
        ),
        "watch_interval_seconds": os.getenv(
            "WATCH_INTERVAL_SECONDS",
            str(DEFAULT_WATCH_INTERVAL_SECONDS),
        ),
    }
    missing = [
        k for k in ("gemini_key", "tg_token", "tg_chat")
        if not cfg[k] or cfg[k].startswith("your_")
    ]
    if missing:
        log.error(
            "The following config keys are not set in %s: %s\n"
            "Fill in the real values in config.env before running the scanner.\n"
            "Recommended commands:\n"
            "  ./run.sh\n"
            "  ./venv/bin/python3 main.py run",
            CONFIG_FILE,
            missing,
        )
        sys.exit(1)

    try:
        cfg["content_char_limit"] = int(cfg["content_char_limit"])
    except ValueError:
        log.error(
            "CONTENT_CHAR_LIMIT in %s must be an integer. Current value: %r",
            CONFIG_FILE,
            cfg["content_char_limit"],
        )
        sys.exit(1)

    if cfg["content_char_limit"] <= 0:
        log.error(
            "CONTENT_CHAR_LIMIT in %s must be greater than 0. Current value: %r",
            CONFIG_FILE,
            cfg["content_char_limit"],
        )
        sys.exit(1)

    try:
        cfg["first_run_lookback_days"] = int(cfg["first_run_lookback_days"])
    except ValueError:
        log.error(
            "FIRST_RUN_LOOKBACK_DAYS in %s must be an integer. Current value: %r",
            CONFIG_FILE,
            cfg["first_run_lookback_days"],
        )
        sys.exit(1)

    if cfg["first_run_lookback_days"] < 0:
        log.error(
            "FIRST_RUN_LOOKBACK_DAYS in %s must be 0 or greater. Current value: %r",
            CONFIG_FILE,
            cfg["first_run_lookback_days"],
        )
        sys.exit(1)

    try:
        cfg["watch_interval_seconds"] = int(cfg["watch_interval_seconds"])
    except ValueError:
        log.error(
            "WATCH_INTERVAL_SECONDS in %s must be an integer. Current value: %r",
            CONFIG_FILE,
            cfg["watch_interval_seconds"],
        )
        sys.exit(1)

    if cfg["watch_interval_seconds"] < 60:
        log.error(
            "WATCH_INTERVAL_SECONDS in %s must be at least 60. Current value: %r",
            CONFIG_FILE,
            cfg["watch_interval_seconds"],
        )
        sys.exit(1)
    return cfg


# ══════════════════════════════════════════════════════════════════════════════
# State  (tracks which post IDs have already been processed)
# ══════════════════════════════════════════════════════════════════════════════

def load_state() -> dict:
    if STATE_FILE.exists():
        raw_state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return normalize_state(raw_state)
    return {}


def save_state(state: dict):
    serializable_state = {}
    for blog_id, blog_state in state.items():
        serializable_state[blog_id] = {
            "seen_ids": list(blog_state.get("seen_ids", [])),
            "summarized_posts": blog_state.get("summarized_posts", {}),
        }

    tmp_file = STATE_FILE.with_suffix(".tmp")
    tmp_file.write_text(
        json.dumps(serializable_state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp_file.replace(STATE_FILE)


def normalize_state(raw_state: dict) -> dict:
    """Upgrade older state formats into a richer per-blog history structure."""
    normalized = {}

    for blog_id, blog_state in raw_state.items():
        if isinstance(blog_state, list):
            seen_ids = [item for item in blog_state if item]
            normalized[blog_id] = {
                "seen_ids": seen_ids,
                "summarized_posts": {},
            }
            continue

        if isinstance(blog_state, dict):
            seen_ids = list({
                *blog_state.get("seen_ids", []),
                *blog_state.get("seen", []),
            })
            summarized_posts = blog_state.get("summarized_posts", {})

            normalized[blog_id] = {
                "seen_ids": [item for item in seen_ids if item],
                "summarized_posts": summarized_posts
                if isinstance(summarized_posts, dict) else {},
            }

    return normalized


def get_blog_state(state: dict, blog_id: str) -> dict:
    blog_state = state.get(blog_id)
    if not isinstance(blog_state, dict):
        blog_state = {"seen_ids": [], "summarized_posts": {}}
        state[blog_id] = blog_state

    blog_state.setdefault("seen_ids", [])
    blog_state.setdefault("summarized_posts", {})
    return blog_state


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


def get_post_id(entry) -> str:
    return entry.get("id", entry.get("link", ""))


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


def entry_datetime(entry) -> Optional[datetime]:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.utcfromtimestamp(calendar.timegm(parsed))

    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if not value:
            continue
        try:
            dt = parsedate_to_datetime(value)
            if dt.tzinfo:
                return dt.astimezone().replace(tzinfo=None)
            return dt
        except (TypeError, ValueError):
            continue

    return None


def first_run_cutoff(lookback_days: int) -> datetime:
    return datetime.now() - timedelta(days=lookback_days)


def load_prompt_template() -> str:
    if not PROMPT_FILE.exists():
        log.error("prompt.md not found at %s — create it before running.", PROMPT_FILE)
        sys.exit(1)
    return PROMPT_FILE.read_text(encoding="utf-8")


def create_http_session() -> requests.Session:
    session = requests.Session()
    return session


# ══════════════════════════════════════════════════════════════════════════════
# Content scraping (mobile Naver)
# ══════════════════════════════════════════════════════════════════════════════

def get_post_content(
    post_url: str,
    session: requests.Session,
    content_char_limit: int,
) -> str:
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

        resp = session.get(mobile_url, headers=HEADERS, timeout=20)
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
            return body.get_text(separator="\n", strip=True)[:content_char_limit]

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
    content_char_limit: int,
    model,
) -> str:
    full_prompt = (
        f"{prompt_template}\n\n"
        f"[Source Data]\n"
        f"Blog: {blog_id}\n"
        f"Title: {title}\n\n"
        f"Content:\n{content[:content_char_limit]}"
    )

    try:
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as exc:
        log.error("Summarization failed: %s", exc)
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# Telegram
# ══════════════════════════════════════════════════════════════════════════════

MAX_TG_CHARS = 4000   # Telegram hard limit is 4096; leave some headroom


def safe_error_message(exc: Exception, secret: str) -> str:
    if not secret:
        return str(exc)
    return str(exc).replace(secret, "***")


def send_telegram(
    text: str,
    token: str,
    chat_id: str,
    session: requests.Session,
):
    """Send a plain-text message to Telegram, splitting into chunks if needed."""
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = [text[i : i + MAX_TG_CHARS] for i in range(0, len(text), MAX_TG_CHARS)]

    for chunk in chunks:
        payload: dict = {"chat_id": chat_id, "text": chunk}
        try:
            r = session.post(api_url, json=payload, timeout=15)
            r.raise_for_status()
            time.sleep(0.5)   # short pause between chunks
        except Exception as exc:
            log.error("Telegram send failed: %s", safe_error_message(exc, token))


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


def mark_seen(blog_state: dict, post_id: str):
    if post_id and post_id not in blog_state["seen_ids"]:
        blog_state["seen_ids"].append(post_id)


def record_summary(
    blog_state: dict,
    post_id: str,
    post_title: str,
    post_url: str,
    post_date: str,
):
    mark_seen(blog_state, post_id)
    blog_state["summarized_posts"][post_id] = {
        "title": post_title,
        "url": post_url,
        "post_date": post_date,
        "summarized_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def should_skip_post(blog_state: dict, post_id: str) -> bool:
    return post_id in blog_state["seen_ids"] or post_id in blog_state["summarized_posts"]


def summarize_entry(
    entry,
    blog_id: str,
    prompt_template: str,
    cfg: dict,
    model,
    session: requests.Session,
    send_to_telegram: bool = True,
    blog_state: Optional[dict] = None,
) -> bool:
    post_id = get_post_id(entry)
    post_title = entry.get("title", "Untitled")
    post_link = entry.get("link", "")
    post_date = entry.get("published", str(datetime.now()))

    log.info("[%s] Summarizing post → %s", blog_id, post_title)

    content = get_post_content(post_link, session, cfg["content_char_limit"])

    if not content:
        raw = entry.get("summary", entry.get("description", ""))
        content = BeautifulSoup(raw, "lxml").get_text(separator="\n", strip=True)

    if not content.strip():
        log.warning("[%s] Empty content — skipping: %s", blog_id, post_title)
        if blog_state is not None:
            mark_seen(blog_state, post_id)
        return False

    content_char_limit = cfg["content_char_limit"]
    was_truncated = len(content) > content_char_limit

    summary = summarize(
        content,
        post_title,
        blog_id,
        prompt_template,
        content_char_limit,
        model,
    )
    if not summary:
        log.warning("[%s] Summarization returned empty result.", blog_id)
        return False

    save_summary_file(blog_id, post_title, post_date, post_link, summary)

    if send_to_telegram:
        truncation_note = ""
        if was_truncated:
            truncation_note = (
                "⚠️ *Partial-content summary:* the original post was longer than "
                f"{content_char_limit:,} characters, so the summary may not cover the full post.\n\n"
            )
        header = (
            f"📰 *New Post — {blog_id}*\n"
            f"*{post_title}*\n"
            f"🗓 {post_date}\n"
            f"🔗 {post_link}\n\n"
        )
        send_telegram(
            header + truncation_note + summary,
            cfg["tg_token"],
            cfg["tg_chat"],
            session,
        )

    if blog_state is not None:
        record_summary(blog_state, post_id, post_title, post_link, post_date)

    return True


# ══════════════════════════════════════════════════════════════════════════════
# Main scan logic
# ══════════════════════════════════════════════════════════════════════════════

def build_model(cfg: dict, model_name: Optional[str] = None):
    selected_model = model_name or cfg["llm_model"]
    genai.configure(api_key=cfg["gemini_key"])
    return genai.GenerativeModel(selected_model)


def scan(
    backfill: bool = False,
    model_name: Optional[str] = None,
    cfg: Optional[dict] = None,
    state: Optional[dict] = None,
    prompt_template: Optional[str] = None,
    model=None,
    session: Optional[requests.Session] = None,
):
    log.info("=" * 60)
    log.info("Naver Blog Scanner — starting run")
    log.info("=" * 60)

    cfg = cfg or load_config()
    state = state if state is not None else load_state()
    blogs = load_blogs()
    prompt_template = prompt_template or load_prompt_template()
    session = session or create_http_session()
    model = model or build_model(cfg, model_name)

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
        blog_state = get_blog_state(state, blog_id)
        cutoff = first_run_cutoff(cfg["first_run_lookback_days"])

        if is_first_run and not backfill:
            older_count = 0
            recent_candidates = 0
            for entry in entries:
                post_id = get_post_id(entry)
                published_at = entry_datetime(entry)
                if published_at and published_at < cutoff:
                    mark_seen(blog_state, post_id)
                    older_count += 1
                else:
                    recent_candidates += 1

            save_state(state)
            log.info(
                "[%s] First run — limited scan to posts from the last %d days. "
                "Marked %d older posts as seen and will process up to %d recent posts.",
                blog_id,
                cfg["first_run_lookback_days"],
                older_count,
                recent_candidates,
            )

        for entry in entries:
            post_id = get_post_id(entry)
            if should_skip_post(blog_state, post_id):
                continue

            state_size_before = (
                len(blog_state["seen_ids"]),
                len(blog_state["summarized_posts"]),
            )
            result = summarize_entry(
                entry,
                blog_id,
                prompt_template,
                cfg,
                model,
                session,
                send_to_telegram=True,
                blog_state=blog_state,
            )
            if result:
                total_new += 1
            state_size_after = (
                len(blog_state["seen_ids"]),
                len(blog_state["summarized_posts"]),
            )
            if state_size_after != state_size_before:
                save_state(state)

            time.sleep(3)   # polite delay between posts

    log.info("Run complete. New posts processed: %d", total_new)


def test_run(model_name: Optional[str] = None):
    log.info("=" * 60)
    log.info("Naver Blog Scanner — starting test run")
    log.info("=" * 60)

    cfg = load_config()
    blogs = load_blogs()
    prompt_template = load_prompt_template()
    session = create_http_session()
    model = build_model(cfg, model_name)

    if not blogs:
        log.warning("No blog URLs found in blogs.txt — nothing to do.")
        return

    blog_url = random.choice(blogs)
    blog_id = extract_blog_id(blog_url)
    if not blog_id:
        log.warning("Cannot parse blog ID from URL: %s", blog_url)
        return

    entries = get_rss_entries(blog_id)
    if not entries:
        log.warning("[%s] No RSS entries returned.", blog_id)
        return

    state = load_state()
    blog_state = get_blog_state(state, blog_id)
    candidates = [
        entry for entry in entries
        if not should_skip_post(blog_state, get_post_id(entry))
    ]
    if not candidates:
        log.warning(
            "[%s] All current feed entries have already been seen. "
            "Test mode will re-summarize a random existing post.",
            blog_id,
        )
    entry = random.choice(candidates or entries)
    log.info("[%s] Test run picked a random post from the feed.", blog_id)
    summarize_entry(
        entry,
        blog_id,
        prompt_template,
        cfg,
        model,
        session,
        send_to_telegram=True,
        blog_state=None,
    )


def watch(
    interval: Optional[int] = None,
    backfill: bool = False,
    model_name: Optional[str] = None,
):
    """Run scans continuously until the user stops the process."""
    run_count = 0
    cfg = load_config()
    interval = interval if interval is not None else cfg["watch_interval_seconds"]
    prompt_template = load_prompt_template()
    session = create_http_session()
    model = build_model(cfg, model_name)
    log.info("Watch mode started. Scan interval: %d seconds", interval)

    while True:
        try:
            run_count += 1
            log.info("Starting watch cycle #%d", run_count)

            # Load the latest state each cycle so manual edits or previous runs are respected.
            state = load_state()
            scan(
                backfill=backfill if run_count == 1 else False,
                cfg=cfg,
                state=state,
                prompt_template=prompt_template,
                model=model,
                session=session,
            )

            log.info("Sleeping for %d seconds. Press Ctrl+C to stop.", interval)
            time.sleep(interval)
        except KeyboardInterrupt:
            log.info("Watch mode stopped by user.")
            break


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Naver Blog Scanner")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Scan once immediately")
    run_parser.add_argument(
        "--backfill",
        action="store_true",
        help=(
            "On first run, summarize ALL existing posts. "
            "Default: only summarize posts from the last 3 days."
        ),
    )
    run_parser.add_argument(
        "--model",
        default=None,
        help=f"LLM model name override. Default comes from LLM_MODEL or {DEFAULT_MODEL}.",
    )

    test_parser = subparsers.add_parser(
        "test", help="Summarize one random post from one blog and send it to Telegram"
    )
    test_parser.add_argument(
        "--model",
        default=None,
        help=f"LLM model name override. Default comes from LLM_MODEL or {DEFAULT_MODEL}.",
    )

    watch_parser = subparsers.add_parser(
        "watch", help="Keep scanning in the terminal at a fixed interval"
    )
    watch_parser.add_argument(
        "--backfill",
        action="store_true",
        help=(
            "Apply backfill only on the first watch cycle. "
            "Later cycles process new posts only."
        ),
    )
    watch_parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help=(
            "Seconds to wait between scans in watch mode. "
            "Overrides WATCH_INTERVAL_SECONDS from config.env."
        ),
    )
    watch_parser.add_argument(
        "--model",
        default=None,
        help=f"LLM model name override. Default comes from LLM_MODEL or {DEFAULT_MODEL}.",
    )

    args = parser.parse_args()
    command = args.command or "run"

    if command == "watch":
        if args.interval is not None and args.interval < 60:
            parser.error("--interval must be at least 60 seconds")
        watch(interval=args.interval, backfill=args.backfill, model_name=args.model)
    elif command == "test":
        test_run(model_name=args.model)
    else:
        scan(backfill=args.backfill, model_name=args.model)

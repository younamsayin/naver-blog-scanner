# Naver Blog Scanner

Scans Naver blogs listed in `blogs.txt` for new posts, summarizes each new post with Gemini, saves summaries locally, and sends them to Telegram.

## What it does

- Reads one or more Naver blog URLs from `blogs.txt`
- Checks each blog's RSS feed for new posts
- Scrapes the post body from the mobile Naver page when possible
- Summarizes each new post with Gemini
- Saves summaries to `summaries/`
- Sends the summary to Telegram

## Setup

1. Create and activate a virtual environment.
2. Install dependencies from `requirements.txt`.
3. Copy `config.env.example` to `config.env` and fill in the values.
4. Copy `blogs.example.txt` to `blogs.txt` or edit `blogs.txt` directly.
5. Run `python3 main.py`.

To process existing posts on the first run, use:

```bash
python3 main.py --backfill
```

## Automation

`setup.sh` installs dependencies, prepares the local folders, and registers a macOS `launchd` job using `com.naverblogscanner.plist` so the scanner can run daily at 9:00 AM.

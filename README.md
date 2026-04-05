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

1. Create the local virtual environment:

```bash
python3 -m venv venv
```

2. Install dependencies into the project virtualenv:

```bash
./venv/bin/pip install -r requirements.txt
```

3. Copy `config.env.example` to `config.env` and fill in the values.
4. Copy `blogs.example.txt` to `blogs.txt` or edit `blogs.txt` directly.
5. Run a one-time scan with the project virtualenv:

```bash
./run.sh
```

or

```bash
./venv/bin/python3 main.py run
```

To process existing posts on the first run, use:

```bash
./venv/bin/python3 main.py run --backfill
```

You can choose the LLM model in either of two ways:

```bash
LLM_MODEL=gemini-2.5-flash
```

or

```bash
./venv/bin/python3 main.py run --model gemini-2.5-flash
```

You can also control how much blog text is sent to the LLM:

```bash
CONTENT_CHAR_LIMIT=12000
```

If a post is longer than that limit, the Telegram message will include a warning before the summary so you know it may not cover the full article.

You can control how far back the first normal run will look before older posts are marked as already seen:

```bash
FIRST_RUN_LOOKBACK_DAYS=3
```

## Run Modes

- Run once immediately:

```bash
./run.sh
```

- Keep it running in your terminal and scan every 15 minutes:

```bash
./venv/bin/python3 main.py watch
```

- Keep it running with a custom interval in seconds:

```bash
./venv/bin/python3 main.py watch --interval 600
```

- Run a one-off test summary from one random post in one blog and send it to Telegram:

```bash
./venv/bin/python3 main.py test
```

`setup.sh` installs dependencies and prepares the local folders. It does not register a scheduled macOS job anymore.

Do not use plain `python3 main.py ...` unless you have already activated the virtualenv. Otherwise Python may not find packages like `feedparser`.

## History Behavior

The scanner keeps `state.json` as a history of seen and summarized post IDs so it does not repeat the same post on future runs.

On a blog's first normal run, it does not walk the entire history. It only considers posts from the last 3 days and marks older feed entries as already seen.

## Launchd Example

The committed [com.naverblogscanner.plist](/Users/eugeniasam/Desktop/code/naver-blog-scanner/com.naverblogscanner.plist) is now an example file with placeholder paths. If you want to use `launchd`, replace `/ABSOLUTE/PATH/TO/naver-blog-scanner` with your actual install path before loading it.

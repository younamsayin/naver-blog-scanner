# Changelog

All notable changes to this project will be documented in this file.

## 2026-04-05

- Added sample publish-safe files: `config.env.example` and `blogs.example.txt`.
- Added `.gitignore` entries to keep local secrets and runtime files out of Git.
- Added `README.md` with setup and usage instructions.
- Changed the scanner from a scheduled `launchd` workflow to explicit terminal commands.
- Added `run` mode for immediate one-time scans.
- Added `watch` mode for continuous scanning with a configurable interval.
- Added `run.sh` as a one-shot helper script that runs the scanner immediately.
- Updated `setup.sh` so it only prepares the local environment and does not register a background job.
- Updated the documentation to prefer `./run.sh` and the project virtualenv over plain `python3`.
- Improved the missing-config startup error message with clearer next steps.
- Added configurable LLM model selection through `LLM_MODEL` and `--model`.
- Added a `test` command that summarizes one random post from one blog and sends it to Telegram.
- Added configurable `CONTENT_CHAR_LIMIT` and a Telegram warning when a summary was generated from truncated post content.
- Changed first normal run behavior to limit processing to posts from the last 3 days.
- Expanded `state.json` handling to keep a durable history of summarized posts and upgrade older state files automatically.
- Fixed UTC handling for RSS timestamps so first-run date filtering is correct outside UTC.
- Fixed state migration to merge both `seen` and `seen_ids` entries instead of dropping one side.
- Added a clear startup error when `prompt.md` is missing.
- Reused the HTTP session and Gemini model across a run instead of rebuilding them for every post.
- Made state writes atomic and masked the Telegram bot token in logged request errors.
- Updated the sample launchd plist to use placeholder paths instead of a personal absolute path.
- Added `WATCH_INTERVAL_SECONDS` so watch-mode timing can be configured from `config.env`.

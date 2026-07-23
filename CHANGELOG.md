# Changelog

All notable changes to this project will be documented in this file.

## 2026-07-23

- Fixed truncated summaries: raised `max_output_tokens` from 4,096 to 16,384 and capped internal thinking at 4,096 tokens, so the model's reasoning can no longer consume the output budget and cut the summary mid-sentence.
- Added a truncation guard: responses ending with `finish_reason=MAX_TOKENS` (or containing no text) now raise and go through the existing retry loop instead of being saved and sent half-finished.
- Migrated from the deprecated `google-generativeai` SDK to `google-genai` (`genai.Client`, `types.GenerateContentConfig`, `types.Part.from_bytes` for images).
- Silenced the new SDK's per-request HTTP log lines so `scanner.log` stays readable.

## 2026-07-17

- Rewrote `prompt.md`: removed the leftover "video" wording, added a 핵심 요약 (TL;DR) section at the top, scaled sections to post substance (2-7 instead of a forced 6-7), capped quotes at 3 verbatim quotes under 20 words, pinned exact Korean headings for consistent output, and stated the investor audience.
- Changed the default model to `gemini-3.5-flash` (full flash tier instead of `-lite`) and set `temperature=0.3` with a `max_output_tokens` backstop for more consistent structured summaries.
- Added post images (up to 4 charts/screenshots per post) to the Gemini request so chart-only data can be summarized; stickers and emoticons are filtered out.
- Marked Naver SE image captions as `[이미지 캡션: ...]` in the extracted text.
- Changed truncation to keep head + tail of long posts instead of cutting off the conclusion, and raised `CONTENT_CHAR_LIMIT` to 100,000.
- Added retry with backoff (3 attempts) for Gemini API failures.
- Restored Telegram formatting via HTML parse mode: `**bold**` now renders as real bold, all content is escaped, and any chunk Telegram rejects is automatically re-sent as plain text.
- Split long Telegram messages at newlines instead of mid-sentence.
- Flagged and labeled full-page-scrape fallbacks so navigation noise is not summarized silently, and lowered the content-container threshold so short posts don't fall through to the noisy fallback.
- Fixed the first-run lookback cutoff to compare timezone-aware UTC datetimes (was skewed by 9 hours on KST) and replaced deprecated `datetime.utcfromtimestamp`.
- Capped per-blog state history at 200 entries so `state.json` stops growing forever.
- Tagged the prior code as `pre-summary-improvements` for easy rollback.

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
- Changed Telegram delivery to plain text only to avoid Markdown parse failures.

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

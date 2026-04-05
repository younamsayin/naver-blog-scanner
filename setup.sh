#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup.sh  —  One-time setup for Naver Blog Scanner
# Run this once after cloning / downloading the project.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║      Naver Blog Scanner — Setup          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Create virtual environment ────────────────────────────────────────────
echo "📦  Creating Python virtual environment..."
cd "$DIR"
python3 -m venv venv
source venv/bin/activate

# ── 2. Install dependencies ───────────────────────────────────────────────────
echo "📦  Installing dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo "    ✅ Dependencies installed."

# ── 3. Create summaries directory ─────────────────────────────────────────────
mkdir -p "$DIR/summaries"

echo ""
echo "════════════════════════════════════════════"
echo "  Setup complete! Next steps:"
echo ""
echo "  1. Open config.env and fill in your:"
echo "       • GEMINI_API_KEY"
echo "       • TELEGRAM_BOT_TOKEN"
echo "       • TELEGRAM_CHAT_ID"
echo ""
echo "  2. Add your blog URLs to blogs.txt"
echo "       (one URL per line)"
echo ""
echo "  3. Run a one-time scan right away:"
echo "       ./venv/bin/python3 main.py run"
echo ""
echo "     Or to summarize all existing posts too:"
echo "       ./venv/bin/python3 main.py run --backfill"
echo ""
echo "  4. Or keep it running in your terminal:"
echo "       ./venv/bin/python3 main.py watch"
echo ""
echo "     Example with a 10-minute interval:"
echo "       ./venv/bin/python3 main.py watch --interval 600"
echo "════════════════════════════════════════════"
echo ""

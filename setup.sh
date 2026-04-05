#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup.sh  —  One-time setup for Naver Blog Scanner
# Run this once after cloning / downloading the project.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_SRC="$DIR/com.naverblogscanner.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.naverblogscanner.plist"

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

# ── 4. Register the daily launchd job ─────────────────────────────────────────
echo "⏰  Registering daily background job (9:00 AM)..."

# Unload previous version if it exists
if launchctl list | grep -q "com.naverblogscanner" 2>/dev/null; then
    launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

cp "$PLIST_SRC" "$PLIST_DST"
launchctl load "$PLIST_DST"
echo "    ✅ Job registered. It will run every day at 9:00 AM."

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
echo "  3. Run the first scan manually:"
echo "       ./venv/bin/python3 main.py"
echo ""
echo "     Or to summarize all existing posts too:"
echo "       ./venv/bin/python3 main.py --backfill"
echo ""
echo "  4. From then on it runs automatically every day at 9 AM."
echo "════════════════════════════════════════════"
echo ""

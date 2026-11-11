#!/usr/bin/env bash
set -e

# Resolve project root directory
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "===================================================="
echo "  Starting Kroma (macOS / Linux)"
echo "===================================================="

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 not found. Please install Python 3.10+."
    exit 1
fi

# Provision .venv if missing
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment in .venv..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

# Open dashboard in browser
if command -v open &> /dev/null; then
    (sleep 1.5 && open "http://localhost:5000") &
elif command -v xdg-open &> /dev/null; then
    (sleep 1.5 && xdg-open "http://localhost:5000") &
fi

# Launch app
python app.py

#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "===================================================="
echo "  Building Kroma Standalone Package (macOS / Linux)"
echo "===================================================="

if [ -f ".venv/bin/python" ]; then
    PYTHON_EXE=".venv/bin/python"
else
    PYTHON_EXE="python3"
fi

if ! "$PYTHON_EXE" -m PyInstaller --version &> /dev/null; then
    echo "PyInstaller not found. Installing PyInstaller..."
    "$PYTHON_EXE" -m pip install pyinstaller
fi

"$PYTHON_EXE" build_exe.py "$@"

echo "===================================================="
echo "  Build completed!"
echo "===================================================="


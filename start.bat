@echo off
REM ProfileHub launcher for Windows: creates a venv on first run, installs deps, starts the app.
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv || (echo Python 3.10+ is required & pause & exit /b 1)
  call .venv\Scripts\activate
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
start "" http://localhost:5000
python app.py
pause

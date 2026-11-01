<div align="center">

# 🌐 Kroma

**Multi-Account Browser Profile Manager & Concurrent Automation Engine**

Manage dozens of persistent Google Chrome profiles, link Google accounts securely via OAuth, import system Chrome profiles, and run automated multi-window browser workflows with real-time countdowns and live logs.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Framework-Flask-000000.svg?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/Database-SQLite-003B57.svg?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-informational.svg)]()
[![Security](https://img.shields.io/badge/Security-Fernet%20AES--256-brightgreen.svg)]()

[Features](#-key-features) •
[Quick Start](#-quick-start) •
[OAuth Setup](#-google-oauth-setup) •
[Automations](#-browser-automations) •
[Architecture](#-architecture) •
[API Reference](#-api-endpoints)

---

</div>

## 📌 Overview

**Kroma** solves multi-account browser isolation and orchestration. It lets you:
1. Connect unlimited Google Accounts using official OAuth 2.0 PKCE.
2. Generate isolated browser profile directories (`data/profiles/<uuid>`) or directly import existing profiles from your local Chrome setup (`Default`, `Profile 1`, etc.).
3. Run concurrent automations across multiple profiles simultaneously—with **independent closing countdowns** per profile, cycle iterations, and live streaming activity logs.
4. Close only targeted browser windows gracefully without affecting your personal browser or external apps (like VS Code, Discord, or Slack).

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 🔐 **Official Google OAuth** | Connects via Google's OAuth consent screen. Identity tokens encrypted at rest via Fernet AES-256. |
| ⚡ **System Chrome Import** | Auto-detects and imports existing signed-in profiles directly from `%LOCALAPPDATA%\Google\Chrome\User Data`. |
| 🎯 **Isolated Profiles** | Generates dedicated user-data directories with separate cookie jars, sessions, and cache. |
| ⏱️ **Concurrent Automations** | Launches multiple profiles at the same time, each running its own independent countdown timer. |
| 📊 **Live Stream Dashboard** | Real-time status cards, countdown progress bars, and streaming console logs without page reloads. |
| 🛡️ **Surgical Process Management** | Tracks Windows window handles (`HWND`) per profile. Sends `WM_CLOSE` to targeted windows only. |

---

## 🚀 Quick Start

### Prerequisites
- [Python 3.10+](https://www.python.org/downloads/)
- Google Chrome or Chromium installed

### Windows (One-Click)
Double-click `start.bat`:
- Auto-provisions `.venv` virtual environment
- Installs dependencies from `requirements.txt`
- Initializes database schema
- Starts web dashboard on `http://localhost:5000`

### Manual Setup
```bash
# 1. Clone repository
git clone https://github.com/your-username/kroma.git
cd kroma

# 2. Create virtual environment
python -m venv .venv

# 3. Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Start app
python app.py
```

Access the dashboard at **[http://localhost:5000](http://localhost:5000)**.

---

## 🔑 Google OAuth Setup

> [!NOTE]
> OAuth linking is optional. If you import system Chrome profiles directly, you can run automations immediately without OAuth credentials.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project → Navigate to **APIs & Services → OAuth consent screen**.
3. Choose **External** user type → Add your target Gmail accounts under **Test users**.
4. Navigate to **Credentials → Create Credentials → OAuth client ID**.
   - Application type: **Web application**
   - Authorized redirect URIs: `http://localhost:5000/oauth/callback`
5. Download client secret JSON and save it as:
   ```
   data/client_secret.json
   ```

---

## 🤖 Browser Automations

Kroma features a multi-threaded automation runner designed for concurrent browsing sessions:

```
[Start Automation]
       │
       ├── Profile 1 ──► [Launch Chrome] ──► [Timer: 30s] ──► [Close Window] ──► Iteration +1
       ├── Profile 2 ──► [Launch Chrome] ──► [Timer: 30s] ──► [Close Window] ──► Iteration +1
       └── Profile 3 ──► [Launch Chrome] ──► [Timer: 30s] ──► [Close Window] ──► Iteration +1
       │
   (Live Polling) ──► Dashboard updates active timers & logs every 1.5s
```

### Automation Modes:
- **Infinite Loop**: Cycles through all selected profiles indefinitely until manually stopped.
- **Cycle Repetitions**: Runs each profile for a user-defined number of iterations.
- **Independent Closing**: Each profile closes as soon as its individual timer finishes; profiles do not block each other.

---

## 🛠️ Project Structure

```
kroma/
├── app.py                      # Flask entry point & routing configuration
├── config.py                   # Environment paths & settings
├── requirements.txt            # Project dependencies
├── start.bat                   # Windows one-click launcher
├── data/                       # Local SQLite DB, encrypted keys & profiles
│   ├── profilehub.db
│   ├── secret.key
│   └── client_secret.json
├── database/
│   ├── db.py                   # SQLite connection & settings helper
│   └── models.py               # Table schemas & startup state recovery
├── modules/
│   ├── browser/
│   │   ├── automation_manager.py  # Threaded automation worker & live telemetry
│   │   ├── chromium.py            # Chrome binary detection & CLI builder
│   │   ├── process_manager.py     # HWND tracking & surgical window closer
│   │   └── profile_manager.py     # Profile CRUD, session cookie detection
│   ├── dashboard/
│   │   └── routes.py              # Dashboard routes & polling API endpoints
│   └── google_auth/
│       ├── account_manager.py     # Account persistence
│       ├── oauth.py               # OAuth 2.0 PKCE implementation
│       └── token_manager.py       # Fernet token encryption
└── templates/                     # Jinja2 HTML templates
    ├── dashboard.html             # Real-time dashboard & streaming logs
    ├── automations.html           # Automation manager & live countdown cards
    ├── accounts.html              # Account manager
    └── profiles.html              # Browser profiles explorer
```

---

## 📡 API Endpoints

Kroma provides live JSON polling APIs:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/dashboard/live` | Returns live stats, active automations, and recent activity logs |
| `GET` | `/api/automations/status` | Returns real-time status of all automations, timers, and iterations |
| `POST` | `/automations/<id>/start` | Triggers background execution threads for automation |
| `POST` | `/automations/<id>/stop` | Gracefully closes all linked profiles and stops execution |

---

## 🔒 Security & Privacy

- **Localhost Bound**: The server binds strictly to `127.0.0.1`.
- **Encrypted Tokens**: Refresh and access tokens are encrypted with Fernet (AES-128 in CBC mode with HMAC SHA-256).
- **CSRF Protection**: Every mutating HTTP POST requires a valid CSRF token.
- **No Password Access**: Uses official Google OAuth scopes (`openid`, `email`, `profile`). No user passwords are ever requested or stored.

---

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).

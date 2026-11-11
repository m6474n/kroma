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
| 🔥 **Firebase Authentication** | Secure dashboard access with Email/Password login powered by Google Identity Platform REST API. |
| 🌐 **Native Proxy / VPN** | HTTP/HTTPS/SOCKS5 per-profile or global tunneling via `--proxy-server`. Auto-connected on launch, zero clicks. |
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

### 📦 Build Windows Standalone Executable (.exe)
To package Kroma into a portable Windows desktop app that runs without requiring Python on target machines:

1. **One-Click Build**:
   Double-click `build.bat` in the project root.

2. **Command Line**:
   ```bash
   python build_exe.py
   # Or for single-file bundle:
   python build_exe.py --onefile
   ```

Output executable is generated at **`dist\Kroma\Kroma.exe`**.
- Auto-extracts templates, static assets, and pre-configured auto-VPN extension.
- Saves SQLite database and browser profiles locally in `dist\Kroma\data\`.
- Auto-opens default web browser to `http://127.0.0.1:5000` on startup.

### ☁️ Vercel Deployment
Kroma is pre-configured for Vercel serverless deployment via [`vercel.json`](vercel.json) and [`api/index.py`](api/index.py).

1. Push repository to GitHub:
   ```bash
   git add .
   git commit -m "feat: ready for vercel"
   git push origin main
   ```
2. Import project in [Vercel Dashboard](https://vercel.com/new).
3. Set Environment Variables in Vercel:
   - `SECRET_KEY`: Random 32-character string
   - `FIREBASE_WEB_API_KEY`: *(Optional)* Your Firebase Web API Key
4. Deploy: Vercel builds the Python WSGI application automatically.

> [!NOTE]
> Vercel hosts the web dashboard, user authentication, and profile telemetry. Launching local desktop Chrome windows and Windows `HWND` automation requires a local/desktop machine.

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

## 🛡️ Urban VPN 1-Click Integration

Kroma includes built-in support for auto-injecting and syncing **Urban VPN** (or any unpacked Chrome extension) across all managed profiles.

### 1. Setup Extension Files
1. Download the unpacked Urban VPN extension folder (ID `eppiocemhmnlbhjplcgkfeedignghneo`).
2. Place the unpacked extension files into:
   ```
   data/extensions/urban_vpn/
   ```
   *(Or specify a custom directory in **Settings → Urban VPN Extension**).*

### 2. Auto-Load on Profile Launch
- When enabled in **Settings**, Kroma passes `--load-extension` automatically whenever any profile is launched (manually or via automations).
- Urban VPN appears in the Chrome toolbar ready to use on startup.

### 3. One-Click VPN State Sync (No-Login or With-Login)
Urban VPN stores consent, privacy agreements, server selection, and account authentication inside Chrome's `Local Extension Settings` LevelDB database.

1. Launch **one profile** (e.g. Master profile).
2. Open Urban VPN:
   - **Without Login**: Accept terms & select your desired country/server.
   - **With Login**: Sign in to your Urban VPN account.
3. Close the profile window.
4. On the **Profiles** page or **Profile Details**, click **⚡ Sync VPN to All**.
5. Kroma replicates the extension's LevelDB state across every profile's `Default/Local Extension Settings/eppiocemhmnlbhjplcgkfeedignghneo`.
6. Every profile now opens pre-authenticated with the VPN pre-configured without needing repeated manual logins or agreement clicks.

---

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
│   ├── client_secret.json
│   └── extensions/             # Unpacked Chrome extensions (Urban VPN)
│       └── urban_vpn/
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
| `POST` | `/profiles/<id>/sync_vpn` | Replicates Urban VPN state from source profile to all other profiles |

---

## 🔒 Security & Privacy

- **Localhost Bound**: The server binds strictly to `127.0.0.1`.
- **Encrypted Tokens**: Refresh and access tokens are encrypted with Fernet (AES-128 in CBC mode with HMAC SHA-256).
- **CSRF Protection**: Every mutating HTTP POST requires a valid CSRF token.
- **No Password Access**: Uses official Google OAuth scopes (`openid`, `email`, `profile`). No user passwords are ever requested or stored.

---

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).

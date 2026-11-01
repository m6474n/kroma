"""Schema definition and initialisation."""
from database.db import db, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS google_accounts (
    id TEXT PRIMARY KEY,
    google_id TEXT UNIQUE NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT,
    avatar_url TEXT,
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    token_expiry INTEGER,
    granted_scopes TEXT,
    connection_status TEXT NOT NULL DEFAULT 'Connected',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS browser_profiles (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES google_accounts(id) ON DELETE CASCADE,
    profile_name TEXT NOT NULL,
    profile_directory TEXT NOT NULL,
    profile_directory_name TEXT,
    browser_status TEXT NOT NULL DEFAULT 'Stopped',
    authentication_status TEXT NOT NULL DEFAULT 'Pending',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS profile_jobs (
    id TEXT PRIMARY KEY,
    account_id TEXT,
    profile_id TEXT,
    job_status TEXT NOT NULL,
    error_message TEXT,
    started_at DATETIME,
    completed_at DATETIME
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS automations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    profile_ids TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL DEFAULT 30,
    is_loop INTEGER NOT NULL DEFAULT 0,
    repeat_count INTEGER NOT NULL DEFAULT 1,
    current_iteration INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'Stopped',
    profile_iterations TEXT NOT NULL DEFAULT '{}',
    last_run_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_profiles_account ON browser_profiles(account_id);
"""


def init_db():
    with db() as conn:
        conn.executescript(SCHEMA)
        try:
            conn.execute("ALTER TABLE automations ADD COLUMN profile_iterations TEXT NOT NULL DEFAULT '{}'")
        except Exception:
            pass
        # Recovery: jobs left 'running' by an interrupted run are marked failed.
        conn.execute(
            "UPDATE profile_jobs SET job_status='failed', error_message='Interrupted (app stopped)', "
            "completed_at=? WHERE job_status IN ('running','pending')",
            (now_iso(),),
        )
        # Recovery: automations left 'Running' when app stopped are marked Stopped.
        conn.execute(
            "UPDATE automations SET status='Stopped' WHERE status='Running'"
        )

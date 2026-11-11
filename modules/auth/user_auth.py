"""Local User Authentication and Password Security."""
import uuid
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import db, now_iso


def has_users() -> bool:
    """Check if any administrator user exists."""
    with db() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
        return bool(row and row["count"] > 0)


def create_user(username: str, password: str) -> tuple[bool, str]:
    """Create a new user with secure password hash."""
    username = username.strip()
    if not username or len(username) < 3:
        return False, "Username must be at least 3 characters."
    if not password or len(password) < 6:
        return False, "Password must be at least 6 characters."

    pwd_hash = generate_password_hash(password)
    user_id = str(uuid.uuid4())
    now = now_iso()

    with db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            return False, "Username already exists."
        conn.execute(
            "INSERT INTO users (id, username, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, pwd_hash, now, now),
        )
    return True, "User created successfully."


def upsert_user(username: str, password: str) -> tuple[bool, str]:
    """Create a user or update password if username already exists locally."""
    username = username.strip()
    if not username or len(username) < 3:
        return False, "Username must be at least 3 characters."
    if not password or len(password) < 6:
        return False, "Password must be at least 6 characters."

    pwd_hash = generate_password_hash(password)
    now = now_iso()

    with db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (pwd_hash, now, existing["id"]),
            )
            return True, "User updated successfully."
        conn.execute(
            "INSERT INTO users (id, username, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), username, pwd_hash, now, now),
        )
    return True, "User created successfully."


def authenticate(username: str, password: str) -> tuple[bool, dict | str]:
    """Verify credentials and return user info."""
    username = username.strip()
    if not username or not password:
        return False, "Please enter both username and password."

    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        return False, "Invalid username or password."

    if not check_password_hash(row["password_hash"], password):
        return False, "Invalid username or password."

    return True, {"id": row["id"], "username": row["username"]}


def update_password(user_id: str, old_password: str, new_password: str) -> tuple[bool, str]:
    """Update user password after verifying old password."""
    if not new_password or len(new_password) < 6:
        return False, "New password must be at least 6 characters."

    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return False, "User not found."

        if not check_password_hash(row["password_hash"], old_password):
            return False, "Current password is incorrect."

        new_hash = generate_password_hash(new_password)
        conn.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                     (new_hash, now_iso(), user_id))

    return True, "Password updated successfully."


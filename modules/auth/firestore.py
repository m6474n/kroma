"""Firebase Cloud Firestore REST API integration for user profiles and subscriptions."""
import os
import requests
from database.db import get_setting, set_setting
from modules.auth.firebase_auth import get_firebase_api_key

FIRESTORE_URL = "https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/{path}"
_http = requests.Session()
_http.headers.update({"User-Agent": "Kroma-Firestore/1.0"})


def get_firebase_project_id() -> str:
    """Return Firebase Project ID from env or database."""
    return (
        os.environ.get("FIREBASE_PROJECT_ID", "").strip()
        or get_setting("firebase_project_id", "").strip()
        or "kroma-26615"
    )


def set_firebase_project_id(project_id: str):
    set_setting("firebase_project_id", project_id.strip())


def to_firestore_val(val):
    if isinstance(val, bool):
        return {"booleanValue": val}
    elif isinstance(val, int):
        return {"integerValue": str(val)}
    elif isinstance(val, float):
        return {"doubleValue": val}
    elif isinstance(val, str):
        return {"stringValue": val}
    elif isinstance(val, list):
        return {"arrayValue": {"values": [to_firestore_val(v) for v in val]}}
    elif isinstance(val, dict):
        return {"mapValue": {"fields": {k: to_firestore_val(v) for k, v in val.items()}}}
    return {"nullValue": None}


def from_firestore_doc(doc: dict) -> dict:
    fields = doc.get("fields", {})
    res = {}
    for k, v in fields.items():
        if "stringValue" in v:
            res[k] = v["stringValue"]
        elif "integerValue" in v:
            try:
                res[k] = int(v["integerValue"])
            except ValueError:
                res[k] = v["integerValue"]
        elif "booleanValue" in v:
            res[k] = v["booleanValue"]
        elif "doubleValue" in v:
            res[k] = float(v["doubleValue"])
        elif "arrayValue" in v:
            res[k] = [from_firestore_val(x) for x in v["arrayValue"].get("values", [])]
        elif "mapValue" in v:
            res[k] = from_firestore_doc(v["mapValue"])
    return res


def from_firestore_val(v: dict):
    for k in ("stringValue", "booleanValue", "doubleValue"):
        if k in v:
            return v[k]
    if "integerValue" in v:
        try:
            return int(v["integerValue"])
        except ValueError:
            return v["integerValue"]
    if "mapValue" in v:
        return from_firestore_doc(v["mapValue"])
    return None


def save_user_profile(user_id: str, profile_data: dict, id_token: str | None = None) -> tuple[bool, str]:
    """Create or update user profile document in Firestore collection 'users'."""
    project_id = get_firebase_project_id()
    api_key = get_firebase_api_key()
    if not api_key:
        return False, "Firebase API Key not configured."

    url = FIRESTORE_URL.format(project_id=project_id, path=f"users/{user_id}")
    url += f"?key={api_key}"

    fields = {k: to_firestore_val(v) for k, v in profile_data.items()}
    headers = {"Content-Type": "application/json"}
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"

    try:
        resp = _http.patch(url, json={"fields": fields}, headers=headers, timeout=10)
        if resp.ok:
            return True, "Profile saved in Firestore successfully."
        try:
            msg = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
            return False, f"Firestore error: {msg}"
        except Exception:
            return False, f"Firestore HTTP error ({resp.status_code})."
    except Exception as exc:
        return False, f"Failed to connect to Firestore: {exc}"


def list_users(id_token: str | None = None) -> tuple[bool, list[dict] | str]:
    """List all user documents from Firestore `users` collection."""
    project_id = get_firebase_project_id()
    api_key = get_firebase_api_key()
    if not api_key:
        return False, "Firebase API Key not configured."

    url = FIRESTORE_URL.format(project_id=project_id, path="users") + f"?key={api_key}&pageSize=200"
    headers = {"Authorization": f"Bearer {id_token}"} if id_token else {}
    try:
        resp = _http.get(url, headers=headers, timeout=12)
        if not resp.ok:
            msg = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
            return False, f"Firestore error: {msg}"
        docs = resp.json().get("documents", [])
        users = []
        for d in docs:
            u = from_firestore_doc(d)
            if "uid" not in u and "name" in d:
                u["uid"] = d["name"].rsplit("/", 1)[-1]
            users.append(u)
        return True, users
    except Exception as exc:
        return False, f"Failed to list users: {exc}"


def update_user_fields(user_id: str, fields: dict, id_token: str | None = None) -> tuple[bool, str]:
    """Partially update specific fields on a Firestore `users/{user_id}` document."""
    project_id = get_firebase_project_id()
    api_key = get_firebase_api_key()
    if not api_key:
        return False, "Firebase API Key not configured."

    mask_params = "&".join(f"updateMask.fieldPaths={k}" for k in fields.keys())
    url = FIRESTORE_URL.format(project_id=project_id, path=f"users/{user_id}") + f"?key={api_key}&{mask_params}"
    headers = {"Content-Type": "application/json"}
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"

    payload = {"fields": {k: to_firestore_val(v) for k, v in fields.items()}}
    try:
        resp = _http.patch(url, json=payload, headers=headers, timeout=10)
        if resp.ok:
            return True, "User updated in Firestore."
        msg = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
        return False, f"Firestore error: {msg}"
    except Exception as exc:
        return False, f"Failed to update user: {exc}"


def get_user_profile(user_id: str, id_token: str | None = None) -> tuple[bool, dict | str]:
    """Fetch user profile document from Firestore."""
    project_id = get_firebase_project_id()
    api_key = get_firebase_api_key()
    if not api_key:
        return False, "Firebase API Key not configured."

    url = FIRESTORE_URL.format(project_id=project_id, path=f"users/{user_id}")
    url += f"?key={api_key}"

    headers = {}
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"

    try:
        resp = _http.get(url, headers=headers, timeout=10)
        if resp.ok:
            return True, from_firestore_doc(resp.json())
        if resp.status_code == 404:
            return False, "User profile not found in Firestore."
        try:
            msg = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
            return False, f"Firestore error: {msg}"
        except Exception:
            return False, f"Firestore HTTP error ({resp.status_code})."
    except Exception as exc:
        return False, f"Failed to connect to Firestore: {exc}"


def list_users(id_token: str | None = None) -> tuple[bool, list[dict] | str]:
    """List all user documents from Firestore `users` collection."""
    project_id = get_firebase_project_id()
    api_key = get_firebase_api_key()
    if not api_key:
        return False, "Firebase API Key not configured."

    url = FIRESTORE_URL.format(project_id=project_id, path="users") + f"?key={api_key}&pageSize=200"
    headers = {"Authorization": f"Bearer {id_token}"} if id_token else {}
    try:
        resp = _http.get(url, headers=headers, timeout=12)
        if not resp.ok:
            msg = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
            return False, f"Firestore error: {msg}"
        docs = resp.json().get("documents", [])
        users = []
        for d in docs:
            u = from_firestore_doc(d)
            if "uid" not in u and "name" in d:
                u["uid"] = d["name"].rsplit("/", 1)[-1]
            users.append(u)
        return True, users
    except Exception as exc:
        return False, f"Failed to list users: {exc}"


def update_user_fields(user_id: str, fields: dict, id_token: str | None = None) -> tuple[bool, str]:
    """Partially update specific fields on a Firestore `users/{user_id}` document."""
    project_id = get_firebase_project_id()
    api_key = get_firebase_api_key()
    if not api_key:
        return False, "Firebase API Key not configured."

    mask_params = "&".join(f"updateMask.fieldPaths={k}" for k in fields.keys())
    url = FIRESTORE_URL.format(project_id=project_id, path=f"users/{user_id}") + f"?key={api_key}&{mask_params}"
    headers = {"Content-Type": "application/json"}
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"

    payload = {"fields": {k: to_firestore_val(v) for k, v in fields.items()}}
    try:
        resp = _http.patch(url, json=payload, headers=headers, timeout=10)
        if resp.ok:
            return True, "User updated in Firestore."
        msg = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
        return False, f"Firestore error: {msg}"
    except Exception as exc:
        return False, f"Failed to update user: {exc}"


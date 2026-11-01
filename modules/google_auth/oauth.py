"""Official Google OAuth 2.0 consent flow (authorization code + PKCE)."""
import os

import requests
from google_auth_oauthlib.flow import Flow

from config import CLIENT_SECRET_PATH, SCOPES, USERINFO_URL

# Local http redirect on localhost is allowed for development.
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
# Google may return scopes in a different order / with extras.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


def client_configured() -> bool:
    return CLIENT_SECRET_PATH.exists()


def _flow(redirect_uri: str, state: str | None = None) -> Flow:
    return Flow.from_client_secrets_file(
        str(CLIENT_SECRET_PATH), scopes=SCOPES, redirect_uri=redirect_uri, state=state
    )


def start(redirect_uri: str):
    """Return (authorization_url, state, code_verifier)."""
    flow = _flow(redirect_uri)
    url, state = flow.authorization_url(
        access_type="offline",
        prompt="select_account consent",  # always pick an account + get a refresh token
    )
    return url, state, flow.code_verifier


def finish(redirect_uri: str, state: str, code_verifier: str, authorization_response: str):
    """Exchange the code for tokens and fetch the Google identity.

    Returns (credentials, userinfo_dict).
    """
    flow = _flow(redirect_uri, state=state)
    flow.code_verifier = code_verifier
    flow.fetch_token(authorization_response=authorization_response)
    creds = flow.credentials
    resp = requests.get(
        USERINFO_URL, headers={"Authorization": f"Bearer {creds.token}"}, timeout=15
    )
    resp.raise_for_status()
    return creds, resp.json()

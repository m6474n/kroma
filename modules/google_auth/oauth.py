"""Official Google OAuth 2.0 consent flow (authorization code + PKCE)."""
import os

import requests
from google_auth_oauthlib.flow import Flow

from config import SCOPES, USERINFO_URL, get_client_secret_config

# Local http redirect on localhost is allowed for development.
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
# Google may return scopes in a different order / with extras.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


def client_configured() -> bool:
    return get_client_secret_config() is not None


def _flow(redirect_uri: str, state: str | None = None) -> Flow:
    cfg = get_client_secret_config()
    if not cfg:
        raise FileNotFoundError("Google OAuth client configuration is missing.")
    return Flow.from_client_config(
        cfg, scopes=SCOPES, redirect_uri=redirect_uri, state=state
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

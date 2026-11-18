"""LinkedIn OAuth 2.0 authorization-code flow.

Scopes: openid+profile (to learn the member id) and w_member_social (to post).
Standard apps get a ~60 day access token and NO refresh token (refresh tokens are
limited to LinkedIn partner programs), so we track expiry and ask you to reconnect.
If LinkedIn does return a refresh token, ensure_fresh() uses it.
"""
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from . import tokens
from .config import settings
from .db import connect

PROVIDER = "linkedin"
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
SCOPES = "openid profile w_member_social"
STATE_TTL_MIN = 10


class OAuthError(Exception):
    pass


def _require_app():
    if not settings.li_client_id or not settings.li_client_secret:
        raise OAuthError("LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET are not set")


def build_login_url() -> str:
    _require_app()
    state = secrets.token_urlsafe(24)
    exp = (datetime.now(timezone.utc) + timedelta(minutes=STATE_TTL_MIN)).isoformat(timespec="seconds")
    with connect() as c:
        c.execute("DELETE FROM oauth_states WHERE expires_at < ?", (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
        c.execute("INSERT INTO oauth_states(state,provider,expires_at) VALUES (?,?,?)", (state, PROVIDER, exp))
    q = {"response_type": "code", "client_id": settings.li_client_id, "redirect_uri": settings.li_redirect,
         "state": state, "scope": SCOPES}
    return f"{AUTH_URL}?{urlencode(q)}"


def _consume_state(state: str) -> bool:
    """Single-use CSRF check."""
    with connect() as c:
        r = c.execute("SELECT expires_at FROM oauth_states WHERE state=? AND provider=?", (state, PROVIDER)).fetchone()
        c.execute("DELETE FROM oauth_states WHERE state=?", (state,))
    return bool(r) and datetime.fromisoformat(r["expires_at"]) > datetime.now(timezone.utc)


def _token_request(data: dict) -> dict:
    try:
        r = httpx.post(TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    except httpx.HTTPError as e:
        raise OAuthError(f"network error talking to LinkedIn: {e}")
    if r.status_code != 200:
        raise OAuthError(f"LinkedIn token endpoint {r.status_code}: {r.text[:200]}")
    return r.json()


def _store(tok: dict, account_id=None, account_name=None, old_refresh=None):
    exp = datetime.now(timezone.utc) + timedelta(seconds=int(tok.get("expires_in", 0)))
    tokens.save(PROVIDER, tok["access_token"], tok.get("refresh_token") or old_refresh,
                exp.isoformat(timespec="seconds"), account_id, account_name)


def handle_callback(code: str, state: str) -> dict:
    if not _consume_state(state):
        raise OAuthError("invalid or expired state; start the connection again")
    _require_app()
    tok = _token_request({"grant_type": "authorization_code", "code": code, "redirect_uri": settings.li_redirect,
                          "client_id": settings.li_client_id, "client_secret": settings.li_client_secret})
    try:
        u = httpx.get(USERINFO_URL, headers={"Authorization": f"Bearer {tok['access_token']}"}, timeout=30)
    except httpx.HTTPError as e:
        raise OAuthError(f"network error fetching profile: {e}")
    if u.status_code != 200:
        raise OAuthError(f"could not read profile ({u.status_code}). Is 'Sign In with LinkedIn using OpenID Connect' enabled on your app?")
    info = u.json()
    if "sub" not in info:
        raise OAuthError("profile response had no member id")
    _store(tok, info["sub"], info.get("name"))
    return tokens.status(PROVIDER)


def get_credentials() -> tuple[str, str]:
    """(access_token, person_id) for publishing; raises OAuthError if unusable."""
    t = tokens.load(PROVIDER)
    if not t:
        raise OAuthError("LinkedIn is not connected")
    exp = datetime.fromisoformat(t["expires_at"]) if t["expires_at"] else None
    if exp and exp - datetime.now(timezone.utc) < timedelta(minutes=5):
        if not t["refresh_token"]:
            raise OAuthError("LinkedIn access token expired; reconnect in the dashboard")
        new = _token_request({"grant_type": "refresh_token", "refresh_token": t["refresh_token"],
                              "client_id": settings.li_client_id, "client_secret": settings.li_client_secret})
        _store(new, t["account_id"], t["account_name"], old_refresh=t["refresh_token"])
        t = tokens.load(PROVIDER)
    return t["access_token"], t["account_id"]

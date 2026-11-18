"""Encrypted OAuth token storage."""
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

from .config import settings
from .db import connect, now_iso


class TokenError(Exception):
    pass


def _fernet() -> Fernet:
    if not settings.enc_key:
        raise TokenError("TOKEN_ENC_KEY is not set")
    try:
        return Fernet(settings.enc_key.encode())
    except ValueError:
        raise TokenError("TOKEN_ENC_KEY is not a valid Fernet key")


def save(provider, access_token, refresh_token=None, expires_at=None, account_id=None, account_name=None):
    f = _fernet()
    enc = lambda s: f.encrypt(s.encode()).decode() if s else None
    with connect() as c:
        c.execute(
            "INSERT INTO oauth_tokens(provider,access_token,refresh_token,expires_at,account_id,account_name,updated_at)"
            " VALUES (?,?,?,?,?,?,?) ON CONFLICT(provider) DO UPDATE SET access_token=excluded.access_token,"
            " refresh_token=excluded.refresh_token, expires_at=excluded.expires_at, account_id=excluded.account_id,"
            " account_name=excluded.account_name, updated_at=excluded.updated_at",
            (provider, enc(access_token), enc(refresh_token), expires_at, account_id, account_name, now_iso()),
        )


def load(provider) -> dict | None:
    with connect() as c:
        r = c.execute("SELECT * FROM oauth_tokens WHERE provider=?", (provider,)).fetchone()
    if not r:
        return None
    f = _fernet()
    try:
        d = dict(r)
        d["access_token"] = f.decrypt(d["access_token"].encode()).decode()
        if d["refresh_token"]:
            d["refresh_token"] = f.decrypt(d["refresh_token"].encode()).decode()
        return d
    except InvalidToken:
        raise TokenError("stored token can't be decrypted (TOKEN_ENC_KEY changed?); reconnect")


def delete(provider):
    with connect() as c:
        c.execute("DELETE FROM oauth_tokens WHERE provider=?", (provider,))


def status(provider) -> dict:
    """Safe-to-expose connection info (never includes the tokens)."""
    with connect() as c:
        r = c.execute("SELECT account_name,expires_at FROM oauth_tokens WHERE provider=?", (provider,)).fetchone()
    if not r:
        return {"connected": False}
    days = None
    if r["expires_at"]:
        days = (datetime.fromisoformat(r["expires_at"]) - datetime.now(timezone.utc)).days
    return {"connected": True, "name": r["account_name"], "expires_at": r["expires_at"],
            "days_left": days, "expired": days is not None and days < 0}

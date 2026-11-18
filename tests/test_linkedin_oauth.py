from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet


class Resp:
    def __init__(self, status=200, js=None, headers=None, text=""):
        self.status_code, self._js, self.headers, self.text = status, js or {}, headers or {}, text

    def json(self): return self._js


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("TOKEN_ENC_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "cid")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "sec")
    from app.db import init_db
    init_db()


def connect_flow(monkeypatch, expires_in=5184000, refresh=None):
    from app import oauth_linkedin as o
    state = parse_qs(urlparse(o.build_login_url()).query)["state"][0]
    tok = {"access_token": "AT", "expires_in": expires_in}
    if refresh:
        tok["refresh_token"] = refresh
    monkeypatch.setattr(o.httpx, "post", lambda *a, **k: Resp(js=tok))
    monkeypatch.setattr(o.httpx, "get", lambda *a, **k: Resp(js={"sub": "abc123", "name": "Sid"}))
    return o, state


def test_login_url_has_scopes_and_state():
    from app import oauth_linkedin as o
    q = parse_qs(urlparse(o.build_login_url()).query)
    assert q["client_id"] == ["cid"] and "w_member_social" in q["scope"][0] and q["state"][0]


def test_callback_stores_encrypted_token(monkeypatch):
    from app import tokens
    from app.db import connect
    o, state = connect_flow(monkeypatch)
    st = o.handle_callback("code", state)
    assert st["connected"] and st["name"] == "Sid" and st["days_left"] >= 59
    raw = connect().execute("SELECT access_token FROM oauth_tokens").fetchone()[0]
    assert "AT" != raw and tokens.load("linkedin")["access_token"] == "AT"
    assert o.get_credentials() == ("AT", "abc123")


def test_bad_or_reused_state_rejected(monkeypatch):
    o, state = connect_flow(monkeypatch)
    with pytest.raises(o.OAuthError):
        o.handle_callback("code", "forged")
    o.handle_callback("code", state)
    with pytest.raises(o.OAuthError):
        o.handle_callback("code", state)  # single use


def test_expired_without_refresh_token_asks_reconnect(monkeypatch):
    o, state = connect_flow(monkeypatch, expires_in=60)
    o.handle_callback("code", state)
    with pytest.raises(o.OAuthError, match="reconnect"):
        o.get_credentials()


def test_refresh_used_when_available(monkeypatch):
    from app import tokens
    o, state = connect_flow(monkeypatch, expires_in=60, refresh="RT")
    o.handle_callback("code", state)
    monkeypatch.setattr(o.httpx, "post", lambda *a, **k: Resp(js={"access_token": "AT2", "expires_in": 5184000}))
    assert o.get_credentials()[0] == "AT2"
    assert tokens.load("linkedin")["refresh_token"] == "RT"  # kept when not rotated


def test_publisher_uses_stored_token(monkeypatch):
    from app.publishers import linkedin as L, PublishError
    o, state = connect_flow(monkeypatch)
    o.handle_callback("code", state)
    seen = {}
    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(h=headers, b=json)
        return Resp(201, headers={"x-restli-id": "urn:li:share:1"})
    monkeypatch.setattr(L.httpx, "post", fake_post)
    pid = L.LinkedInPublisher().publish({"content": "hi", "media_type": "none"})
    assert pid == "urn:li:share:1" and seen["h"]["Authorization"] == "Bearer AT" and seen["b"]["author"] == "urn:li:person:abc123"


def test_publisher_not_connected_is_non_retryable():
    from app.publishers import linkedin as L, PublishError
    with pytest.raises(PublishError) as e:
        L.LinkedInPublisher().publish({"content": "hi", "media_type": "none"})
    assert e.value.retryable is False

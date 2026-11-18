import os

import pytest
from fastapi.testclient import TestClient

H = {"Authorization": "Bearer secret"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("DASHBOARD_TOKEN", "secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("PUBLISH_MODE", "mock")
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_requires_auth(client):
    assert client.get("/api/posts").status_code == 401
    assert client.get("/api/posts", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_draft_and_schedule_flow(client):
    r = client.post("/api/draft", headers=H, json={"idea": "Built a bus tracker at a hackathon"})
    assert r.status_code == 200 and {p["platform"] for p in r.json()} == {"linkedin", "instagram"}
    pid = r.json()[0]["id"]
    s = client.post(f"/api/posts/{pid}/schedule", headers=H, json={"scheduled_at": "2099-01-01T09:00:00+05:30"})
    assert s.status_code == 200 and s.json()["scheduled_at"].startswith("2099-01-01T03:30")
    assert client.post(f"/api/posts/{pid}/schedule", headers=H, json={"scheduled_at": "2099-01-01T09:00:00"}).status_code == 400
    assert client.get("/api/posts/999", headers=H).status_code in (404, 405)


def test_parse_claude_json():
    from app.drafting import _parse
    out = _parse('Sure!\n{"linkedin":"Hi","instagram":"Yo","hashtags":["#a","b"]}')
    assert out["instagram"].endswith("#a #b") and out["linkedin"] == "Hi"

import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ["PUBLISH_MODE"] = "mock"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    from app.db import init_db
    init_db()


def iso(delta_min):
    return (datetime.now(timezone.utc) + timedelta(minutes=delta_min)).isoformat()


def test_due_post_is_published():
    from app import service
    p = service.create_post("linkedin", "hello")
    service.approve(p["id"], iso(-1))
    assert service.process_due() == 1
    r = service.get_post(p["id"])
    assert r["status"] == "published" and r["external_id"].startswith("mock-")


def test_future_post_not_published():
    from app import service
    p = service.create_post("linkedin", "later")
    service.approve(p["id"], iso(60))
    assert service.process_due() == 0
    assert service.get_post(p["id"])["status"] == "scheduled"


def test_draft_never_published():
    from app import service
    service.create_post("linkedin", "draft")
    assert service.process_due() == 0


def test_naive_time_rejected():
    from app import service
    p = service.create_post("linkedin", "x")
    with pytest.raises(ValueError):
        service.approve(p["id"], "2026-11-20T09:00:00")


def test_retry_then_fail(monkeypatch):
    from app import service
    from app.publishers import PublishError

    class Boom:
        def publish(self, post): raise PublishError("500")

    monkeypatch.setattr(service, "get_publisher", lambda platform: Boom())
    p = service.create_post("linkedin", "x")
    service.approve(p["id"], iso(-1))
    t = datetime.now(timezone.utc)
    service.process_due(t)
    r = service.get_post(p["id"])
    assert r["status"] == "scheduled" and r["attempts"] == 1
    service.process_due(t + timedelta(minutes=6))
    service.process_due(t + timedelta(minutes=30))
    r = service.get_post(p["id"])
    assert r["status"] == "failed" and r["attempts"] == 3


def test_non_retryable_fails_immediately(monkeypatch):
    from app import service
    from app.publishers import PublishError

    class Bad:
        def publish(self, post): raise PublishError("401", retryable=False)

    monkeypatch.setattr(service, "get_publisher", lambda platform: Bad())
    p = service.create_post("linkedin", "x")
    service.approve(p["id"], iso(-1))
    service.process_due()
    assert service.get_post(p["id"])["status"] == "failed"


def test_published_is_immutable():
    from app import service
    p = service.create_post("linkedin", "x")
    service.approve(p["id"], iso(-1))
    service.process_due()
    with pytest.raises(ValueError):
        service.update_post(p["id"], content="changed")


def test_recover_stuck_marks_failed_not_retried():
    from app import service
    from app.db import connect
    p = service.create_post("linkedin", "x")
    with connect() as c:
        c.execute("UPDATE posts SET status='publishing' WHERE id=?", (p["id"],))
    service.recover_stuck()
    assert service.get_post(p["id"])["status"] == "failed"

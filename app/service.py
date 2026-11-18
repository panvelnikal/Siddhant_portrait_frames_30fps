"""Post queue logic: CRUD, state transitions, and the due-post processor."""
import json
import logging
from datetime import datetime, timedelta, timezone

from .db import connect, now_iso, row_to_dict
from .publishers import PublishError, get_publisher

log = logging.getLogger("service")
MAX_ATTEMPTS = 3
BACKOFF_MIN = [5, 15]  # minutes before retry 2 and 3


def create_post(platform, content, media_urls=None, media_type="none", status="draft", scheduled_at=None) -> dict:
    ts = now_iso()
    with connect() as c:
        cur = c.execute(
            "INSERT INTO posts(platform,content,media_urls,media_type,scheduled_at,status,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (platform, content, json.dumps(media_urls or []), media_type, scheduled_at, status, ts, ts),
        )
        return get_post(cur.lastrowid, c)


def get_post(pid: int, conn=None) -> dict | None:
    c = conn or connect()
    r = c.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
    return row_to_dict(r) if r else None


def list_posts(status: str | None = None) -> list[dict]:
    with connect() as c:
        q, args = "SELECT * FROM posts", ()
        if status:
            q, args = q + " WHERE status=?", (status,)
        return [row_to_dict(r) for r in c.execute(q + " ORDER BY COALESCE(scheduled_at, created_at)", args)]


def update_post(pid: int, **fields) -> dict | None:
    """Edit content/media/time. Published or in-flight posts are immutable."""
    p = get_post(pid)
    if not p:
        return None
    if p["status"] in ("publishing", "published"):
        raise ValueError(f"cannot edit a {p['status']} post")
    allowed = {"content", "media_urls", "media_type", "scheduled_at"}
    sets, args = [], []
    for k, v in fields.items():
        if k == "scheduled_at" and v is not None:
            v = parse_utc(v).isoformat(timespec="seconds")
        if k in allowed and v is not None:
            sets.append(f"{k}=?")
            args.append(json.dumps(v) if k == "media_urls" else v)
    if sets:
        with connect() as c:
            c.execute(f"UPDATE posts SET {','.join(sets)}, updated_at=? WHERE id=?", (*args, now_iso(), pid))
    return get_post(pid)


def approve(pid: int, scheduled_at: str) -> dict:
    """draft/failed -> scheduled. scheduled_at must be an ISO time with timezone."""
    t = parse_utc(scheduled_at)
    p = get_post(pid)
    if not p:
        raise LookupError("not found")
    if p["status"] not in ("draft", "failed", "scheduled"):
        raise ValueError(f"cannot schedule a {p['status']} post")
    with connect() as c:
        c.execute(
            "UPDATE posts SET status='scheduled', scheduled_at=?, attempts=0, error=NULL, updated_at=? WHERE id=?",
            (t.isoformat(timespec="seconds"), now_iso(), pid),
        )
    return get_post(pid)


def unschedule(pid: int) -> dict:
    p = get_post(pid)
    if not p:
        raise LookupError("not found")
    if p["status"] != "scheduled":
        raise ValueError("only scheduled posts can be unscheduled")
    with connect() as c:
        c.execute("UPDATE posts SET status='draft', updated_at=? WHERE id=?", (now_iso(), pid))
    return get_post(pid)


def delete_post(pid: int):
    p = get_post(pid)
    if p and p["status"] == "publishing":
        raise ValueError("cannot delete a post being published")
    with connect() as c:
        c.execute("DELETE FROM posts WHERE id=?", (pid,))


def parse_utc(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("scheduled_at must include a timezone offset")
    return d.astimezone(timezone.utc)


def process_due(now: datetime | None = None) -> int:
    """Publish every scheduled post that is due. Returns number attempted."""
    now = now or datetime.now(timezone.utc)
    done = 0
    while True:
        with connect() as c:
            # Atomic claim so two overlapping runs never double-post.
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                "SELECT * FROM posts WHERE status='scheduled' AND scheduled_at<=? ORDER BY scheduled_at LIMIT 1",
                (now.isoformat(timespec="seconds"),),
            ).fetchone()
            if not row:
                c.execute("COMMIT")
                return done
            c.execute("UPDATE posts SET status='publishing', updated_at=? WHERE id=?", (now_iso(), row["id"]))
            c.execute("COMMIT")
        post = row_to_dict(row)
        _publish_one(post, now)
        done += 1


def _publish_one(post: dict, now: datetime):
    try:
        ext = get_publisher(post["platform"]).publish(post)
    except PublishError as e:
        _record_failure(post, str(e), e.retryable, now)
    except Exception as e:  # never let one bad post kill the loop
        log.exception("unexpected publish error")
        _record_failure(post, f"unexpected: {e}", False, now)
    else:
        with connect() as c:
            c.execute(
                "UPDATE posts SET status='published', external_id=?, error=NULL, attempts=attempts+1, updated_at=? WHERE id=?",
                (ext, now_iso(), post["id"]),
            )
        log.info("published post %s -> %s", post["id"], ext)


def _record_failure(post: dict, msg: str, retryable: bool, now: datetime):
    attempts = post["attempts"] + 1
    with connect() as c:
        if retryable and attempts < MAX_ATTEMPTS:
            nxt = (now + timedelta(minutes=BACKOFF_MIN[attempts - 1])).isoformat(timespec="seconds")
            c.execute(
                "UPDATE posts SET status='scheduled', scheduled_at=?, attempts=?, error=?, updated_at=? WHERE id=?",
                (nxt, attempts, msg, now_iso(), post["id"]),
            )
            log.warning("post %s failed (attempt %s), retry at %s: %s", post["id"], attempts, nxt, msg)
        else:
            c.execute(
                "UPDATE posts SET status='failed', attempts=?, error=?, updated_at=? WHERE id=?",
                (attempts, msg, now_iso(), post["id"]),
            )
            log.error("post %s failed permanently: %s", post["id"], msg)


def recover_stuck():
    """On startup, posts left 'publishing' by a crash are marked failed (not retried:
    they may have actually gone out, and a duplicate post is worse than a missed one)."""
    with connect() as c:
        c.execute(
            "UPDATE posts SET status='failed', error='interrupted mid-publish; check the platform before retrying',"
            " updated_at=? WHERE status='publishing'",
            (now_iso(),),
        )

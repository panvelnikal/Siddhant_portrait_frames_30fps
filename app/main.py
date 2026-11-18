import hmac
import logging
from urllib.parse import quote
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import drafting, oauth_linkedin, service, tokens
from .config import settings
from .db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
scheduler = BackgroundScheduler(timezone="UTC")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    service.recover_stuck()
    scheduler.add_job(service.process_due, "interval", seconds=30, max_instances=1, coalesce=True)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Social Scheduler", lifespan=lifespan)


def auth(authorization: str = Header(default="")):
    tok = settings.dashboard_token
    given = authorization.removeprefix("Bearer ").strip()
    if not tok or not hmac.compare_digest(tok, given):
        raise HTTPException(401, "invalid or missing token (set DASHBOARD_TOKEN)")


class DraftReq(BaseModel):
    idea: str = Field(min_length=3, max_length=4000)
    platforms: list[str] = ["linkedin", "instagram"]


class PostIn(BaseModel):
    platform: str
    content: str = Field(min_length=1, max_length=3000)
    media_urls: list[str] = []
    media_type: str = "none"


class PostPatch(BaseModel):
    content: str | None = Field(default=None, max_length=3000)
    media_urls: list[str] | None = None
    media_type: str | None = None
    scheduled_at: str | None = None


class ScheduleReq(BaseModel):
    scheduled_at: str  # ISO 8601 with offset, e.g. 2026-11-20T09:00:00+05:30


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except LookupError:
        raise HTTPException(404, "post not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent.parent / "static" / "index.html")


@app.get("/api/config", dependencies=[Depends(auth)])
def config():
    return {"publish_mode": settings.publish_mode, "tz": settings.tz_name, "ai": bool(settings.anthropic_key)}


@app.post("/api/draft", dependencies=[Depends(auth)])
def make_drafts(req: DraftReq):
    out = drafting.draft(req.idea)
    posts = [service.create_post(p, out[p]) for p in req.platforms if p in ("linkedin", "instagram") and out.get(p)]
    return posts


@app.get("/api/posts", dependencies=[Depends(auth)])
def posts(status: str | None = None):
    return service.list_posts(status)


@app.post("/api/posts", dependencies=[Depends(auth)])
def new_post(p: PostIn):
    if p.platform not in ("linkedin", "instagram"):
        raise HTTPException(400, "platform must be linkedin or instagram")
    return _guard(service.create_post, p.platform, p.content, p.media_urls, p.media_type)


@app.patch("/api/posts/{pid}", dependencies=[Depends(auth)])
def edit_post(pid: int, p: PostPatch):
    r = _guard(service.update_post, pid, **p.model_dump())
    if r is None:
        raise HTTPException(404, "post not found")
    return r


@app.post("/api/posts/{pid}/schedule", dependencies=[Depends(auth)])
def schedule(pid: int, s: ScheduleReq):
    return _guard(service.approve, pid, s.scheduled_at)


@app.post("/api/posts/{pid}/unschedule", dependencies=[Depends(auth)])
def unschedule(pid: int):
    return _guard(service.unschedule, pid)


@app.delete("/api/posts/{pid}", dependencies=[Depends(auth)])
def remove(pid: int):
    _guard(service.delete_post, pid)
    return {"ok": True}


# ---- LinkedIn connection ----
@app.get("/api/linkedin/status", dependencies=[Depends(auth)])
def li_status():
    try:
        return tokens.status("linkedin")
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/linkedin/connect", dependencies=[Depends(auth)])
def li_connect():
    """Returns the LinkedIn consent URL; the dashboard navigates the browser to it."""
    try:
        tokens._fernet()  # fail early if the encryption key is missing
        return {"url": oauth_linkedin.build_login_url()}
    except (oauth_linkedin.OAuthError, tokens.TokenError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/linkedin/disconnect", dependencies=[Depends(auth)])
def li_disconnect():
    tokens.delete("linkedin")
    return {"ok": True}


@app.get("/auth/linkedin/callback")
def li_callback(code: str = "", state: str = "", error: str = "", error_description: str = ""):
    """Browser lands here from LinkedIn. Protected by the single-use `state` created in /connect."""
    if error:
        return RedirectResponse(f"/?li=error&msg={quote(error_description or error)}")
    try:
        oauth_linkedin.handle_callback(code, state)
    except (oauth_linkedin.OAuthError, tokens.TokenError) as e:
        return RedirectResponse(f"/?li=error&msg={quote(str(e))}")
    return RedirectResponse("/?li=ok")

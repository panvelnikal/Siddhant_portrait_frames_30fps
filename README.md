# Social Scheduler

Draft with Claude, approve, schedule, auto-post to LinkedIn and Instagram.
Phase 1: drafting, queue, scheduler with retries, dashboard, LinkedIn text posts. Default `PUBLISH_MODE=mock` only logs.

## Run
```
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env   # set DASHBOARD_TOKEN at minimum
uvicorn app.main:app --reload
```
Open http://localhost:8000 and enter the token. Run tests with `pytest`.

## How it works
`draft -> scheduled -> publishing -> published | failed`. A job runs every 30s, claims due posts atomically, retries retryable errors (5 and 15 min backoff, 3 attempts). Posts interrupted mid-publish are marked failed on restart rather than retried, to avoid duplicate posts.

## Roadmap
- Phase 2: Instagram image/carousel, media storage, LinkedIn images, LinkedIn OAuth + token refresh
- Phase 3: reels, calendar view, failure alerts, analytics

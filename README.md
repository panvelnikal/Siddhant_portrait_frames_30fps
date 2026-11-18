# Social Scheduler

Draft with Claude, approve, schedule, auto-post to LinkedIn and Instagram.
Phase 1: drafting, queue, scheduler with retries, dashboard, LinkedIn OAuth + text posts. Default `PUBLISH_MODE=mock` only logs.

## Run
```
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env   # set DASHBOARD_TOKEN at minimum
uvicorn app.main:app --reload
```
Open http://localhost:8000 and enter the token. Run tests with `pytest`.

## Connect LinkedIn
1. At linkedin.com/developers create an app, then under Products add **Share on LinkedIn** and **Sign In with LinkedIn using OpenID Connect** (both self-serve).
2. Under Auth, add the redirect URL `http://localhost:8000/auth/linkedin/callback` (must match `LINKEDIN_REDIRECT_URI` exactly; use your https URL once deployed).
3. Put the Client ID/Secret in `.env`, and generate `TOKEN_ENC_KEY` (command in `.env.example`).
4. In the dashboard click **Connect** on the LinkedIn card.

Tokens are stored encrypted in SQLite. Standard LinkedIn apps get a ~60 day token with no refresh token, so the dashboard shows days left and you click **Reconnect** before it expires. A post scheduled after expiry fails with a clear message instead of retrying.

## How it works
`draft -> scheduled -> publishing -> published | failed`. A job runs every 30s, claims due posts atomically, retries retryable errors (5 and 15 min backoff, 3 attempts). Posts interrupted mid-publish are marked failed on restart rather than retried, to avoid duplicate posts.

## Roadmap
- Phase 2: Instagram image/carousel, media storage, LinkedIn images, LinkedIn image posts
- Phase 3: reels, calendar view, failure alerts, analytics

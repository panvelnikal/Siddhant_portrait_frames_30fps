import os
from pathlib import Path


def _load_dotenv():
    p = Path(".env")
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


class Settings:
    @property
    def dashboard_token(self): return os.getenv("DASHBOARD_TOKEN", "")
    @property
    def tz_name(self): return os.getenv("TZ_NAME", "Asia/Kolkata")
    @property
    def publish_mode(self): return os.getenv("PUBLISH_MODE", "mock")
    @property
    def anthropic_key(self): return os.getenv("ANTHROPIC_API_KEY", "")
    @property
    def claude_model(self): return os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
    @property
    def li_token(self): return os.getenv("LINKEDIN_ACCESS_TOKEN", "")
    @property
    def li_person(self): return os.getenv("LINKEDIN_PERSON_ID", "")
    @property
    def li_version(self): return os.getenv("LINKEDIN_API_VERSION", "202510")
    @property
    def li_client_id(self): return os.getenv("LINKEDIN_CLIENT_ID", "")
    @property
    def li_client_secret(self): return os.getenv("LINKEDIN_CLIENT_SECRET", "")
    @property
    def li_redirect(self): return os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:8000/auth/linkedin/callback")
    @property
    def enc_key(self): return os.getenv("TOKEN_ENC_KEY", "")
    @property
    def db_path(self): return os.getenv("DB_PATH", "data/scheduler.db")
    @property
    def tone_path(self): return os.getenv("TONE_PATH", "data/tone.txt")


settings = Settings()

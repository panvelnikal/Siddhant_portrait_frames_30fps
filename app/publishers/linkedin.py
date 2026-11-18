import httpx

from .. import oauth_linkedin, tokens
from ..config import settings
from .base import PublishError, Publisher

API = "https://api.linkedin.com/rest/posts"


class LinkedInPublisher(Publisher):
    """Text posts to a personal profile. Image/video upload comes in a later phase."""

    def publish(self, post: dict) -> str:
        try:
            token, person = oauth_linkedin.get_credentials()
        except (oauth_linkedin.OAuthError, tokens.TokenError) as e:
            raise PublishError(str(e), retryable=False)
        if post["media_type"] != "none":
            raise PublishError("LinkedIn media posts not implemented yet", retryable=False)
        body = {
            "author": f"urn:li:person:{person}",
            "commentary": post["content"],
            "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "LinkedIn-Version": settings.li_version,
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }
        try:
            r = httpx.post(API, json=body, headers=headers, timeout=30)
        except httpx.HTTPError as e:
            raise PublishError(f"network error: {e}")
        if r.status_code == 201:
            return r.headers.get("x-restli-id", "unknown")
        # 401/403 = token problem, 4xx other = bad request: retrying will not help
        retryable = r.status_code >= 500 or r.status_code == 429
        raise PublishError(f"LinkedIn {r.status_code}: {r.text[:300]}", retryable=retryable)

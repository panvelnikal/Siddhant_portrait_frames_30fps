import httpx

from ..config import settings
from .base import PublishError, Publisher

API = "https://api.linkedin.com/rest/posts"


class LinkedInPublisher(Publisher):
    """Text posts to a personal profile. Image/video upload comes in a later phase."""

    def publish(self, post: dict) -> str:
        if not settings.li_token or not settings.li_person:
            raise PublishError("LINKEDIN_ACCESS_TOKEN / LINKEDIN_PERSON_ID not set", retryable=False)
        if post["media_type"] != "none":
            raise PublishError("LinkedIn media posts not implemented yet", retryable=False)
        body = {
            "author": f"urn:li:person:{settings.li_person}",
            "commentary": post["content"],
            "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        headers = {
            "Authorization": f"Bearer {settings.li_token}",
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

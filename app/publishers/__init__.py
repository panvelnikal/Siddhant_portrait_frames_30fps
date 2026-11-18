from ..config import settings
from .base import PublishError, Publisher
from .instagram import InstagramPublisher
from .linkedin import LinkedInPublisher
from .mock import MockPublisher


def get_publisher(platform: str) -> Publisher:
    if settings.publish_mode != "live":
        return MockPublisher(platform)
    return {"linkedin": LinkedInPublisher, "instagram": InstagramPublisher}[platform]()


__all__ = ["get_publisher", "PublishError", "Publisher"]

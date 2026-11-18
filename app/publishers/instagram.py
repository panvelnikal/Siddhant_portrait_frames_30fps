from .base import PublishError, Publisher


class InstagramPublisher(Publisher):
    """Phase 2: Graph API container -> publish flow (image, carousel, reel)."""

    def publish(self, post: dict) -> str:
        raise PublishError("Instagram publishing not implemented yet (phase 2)", retryable=False)

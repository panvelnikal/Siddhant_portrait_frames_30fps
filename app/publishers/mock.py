import logging
import uuid

from .base import Publisher

log = logging.getLogger("publisher.mock")


class MockPublisher(Publisher):
    def __init__(self, platform: str):
        self.platform = platform

    def publish(self, post: dict) -> str:
        log.info("[MOCK %s] would publish (%s): %r", self.platform, post["media_type"], post["content"][:80])
        return f"mock-{self.platform}-{uuid.uuid4().hex[:8]}"

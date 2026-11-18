class PublishError(Exception):
    """Raised when publishing fails. retryable=False skips further retries."""

    def __init__(self, msg: str, retryable: bool = True):
        super().__init__(msg)
        self.retryable = retryable


class Publisher:
    def publish(self, post: dict) -> str:
        """Publish and return the platform's post id/urn."""
        raise NotImplementedError

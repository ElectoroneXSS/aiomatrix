class AiomatrixError(Exception):
    """Base exception."""

class NetworkError(AiomatrixError):
    pass

class APIError(AiomatrixError):
    def __init__(self, description, *, method=None, status=None, payload=None):
        self.description, self.method, self.status, self.payload = description, method, status, payload
        msg = f"{method or 'API'}: {description}"
        if status is not None:
            msg += f" (HTTP {status})"
        super().__init__(msg)

class ValidationError(AiomatrixError, ValueError):
    pass

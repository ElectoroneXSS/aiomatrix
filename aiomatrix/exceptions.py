"""Exception hierarchy for aiomatrix."""
class AiomatrixError(Exception): """Base exception for the library."""
class NetworkError(AiomatrixError): """Transport, DNS, TLS, or timeout error."""
class ValidationError(AiomatrixError, ValueError): """Invalid local input."""
class APIError(AiomatrixError):
    def __init__(self, description, *, method=None, status=None, payload=None, error_code=None):
        self.description, self.method, self.status = str(description), method, status
        self.payload, self.error_code = payload, error_code
        msg = f"{method or 'API'}: {self.description}"
        if status is not None: msg += f" (HTTP {status})"
        if error_code is not None: msg += f" [code={error_code}]"
        super().__init__(msg)
class RetryAfter(APIError):
    def __init__(self, description='Rate limited', *, retry_after=1, **kwargs):
        self.retry_after = max(0, float(retry_after)); super().__init__(description, **kwargs)

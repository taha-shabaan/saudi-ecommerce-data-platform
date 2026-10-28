"""Custom exception hierarchy for the Saudi eCommerce Data Platform.

Following the platform error-handling standard:
- TransientError: Network timeouts, rate limits, temporary unavailability. Eligible for exponential backoff retries.
- PermanentError: Schema validation failures, 400 Bad Request, invalid business logic. Dead-lettered immediately.
- DataQualityError: Circuit breaker exceptions when Tier 1 invariant assertions fail.
"""

from typing import Any


class PlatformError(Exception):
    """Base exception for all data platform errors with structured context."""

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_PLATFORM_ERROR",
        id_correlation: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.id_correlation = id_correlation
        self.context = context or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize error details for structured JSON logging."""
        return {
            "error_class": self.__class__.__name__,
            "error_code": self.error_code,
            "error_message": self.message,
            "id_correlation": self.id_correlation,
            "context": self.context,
        }


class TransientError(PlatformError):
    """Transient failure that will likely resolve on retry (e.g., connection timeout, 429, 503)."""

    def __init__(
        self,
        message: str,
        error_code: str = "TRANSIENT_UPSTREAM_ERROR",
        id_correlation: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, id_correlation=id_correlation, context=context)


class PermanentError(PlatformError):
    """Permanent failure that will NOT resolve with retries (e.g., malformed payload, 400, 401)."""

    def __init__(
        self,
        message: str,
        error_code: str = "PERMANENT_CONTRACT_ERROR",
        id_correlation: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, id_correlation=id_correlation, context=context)


class DataQualityError(PlatformError):
    """Circuit breaker failure when Tier 1 quality invariant checks fail (ADR-0004)."""

    def __init__(
        self,
        message: str,
        error_code: str = "DATA_QUALITY_CIRCUIT_BREAKER",
        id_correlation: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, id_correlation=id_correlation, context=context)


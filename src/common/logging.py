"""Structured JSON logger with correlation ID tracking and PII sanitization.

Adheres to enterprise observability standards:
- Outputs machine-readable JSON on stdout.
- Masks sensitive keys (password, secret, token, card_number, ssn, cvv).
- Attaches correlation identifiers (`id_correlation`, `id_trace`) across execution steps.
"""

from datetime import datetime, timezone
import json
import logging
import sys
from typing import Any, Dict, Optional
import uuid

# Keys that must never appear in raw application logs
SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "card_number",
    "pan",
    "cvv",
    "ssn",
    "national_id",
    "api_key",
    "auth",
}


def sanitize_payload(obj: Any) -> Any:
    """Recursively mask sensitive values by key name."""
    if isinstance(obj, dict):
        sanitized = {}
        for key, value in obj.items():
            if any(sensitive in key.lower() for sensitive in SENSITIVE_KEYS):
                sanitized[key] = "********"
            else:
                sanitized[key] = sanitize_payload(value)
        return sanitized
    elif isinstance(obj, list):
        return [sanitize_payload(item) for item in obj]
    return obj


class JSONFormatter(logging.Formatter):
    """Custom formatter producing structured JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "id_correlation": getattr(record, "id_correlation", None),
            "id_trace": getattr(record, "id_trace", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "module": record.module,
            "line": record.lineno,
        }

        # Attach extra structured payload if supplied
        extra_data = getattr(record, "payload", None)
        if extra_data:
            log_payload["payload"] = sanitize_payload(extra_data)

        # Attach exception info if present
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_payload, ensure_ascii=False)


def get_logger(name: str = "saudi_ecom_platform", level: str = "INFO") -> logging.Logger:
    """Build or retrieve a configured structured JSON logger."""
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if logger was already initialized
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


def generate_correlation_id(prefix: str = "wf_ecom") -> str:
    """Generate a unique correlation ID for pipeline execution tracing."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


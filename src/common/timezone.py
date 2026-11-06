"""Saudi Arabia Timezone (Asia/Riyadh / AST) Management & Partition Alignment.

Provides centralized timezone utilities conforming to GLOSSARY.md and README.md:
- Timezone standard: Asia/Riyadh (Arabia Standard Time, AST, UTC+3, fixed offset).
- Operational Alignment: Partition keys (year=YYYY/month=MM/day=DD) and business day
  reporting views are aligned with Saudi Arabia operational time.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src.common.config import settings

# Canonical Saudi Arabia Timezone (Asia/Riyadh, AST, UTC+3)
SAUDI_TIMEZONE = ZoneInfo(settings.default_timezone)


def saudi_now() -> datetime:
    """Return the current timestamp in Saudi Arabia time (Asia/Riyadh, AST, UTC+3)."""
    return datetime.now(tz=SAUDI_TIMEZONE)


def to_saudi_time(dt: datetime) -> datetime:
    """Convert any timezone-aware or naive datetime to Saudi Arabia time (Asia/Riyadh)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=SAUDI_TIMEZONE)
    return dt.astimezone(SAUDI_TIMEZONE)


def format_ast(dt: datetime) -> str:
    """Format datetime as an ISO-8601 string in Saudi Arabia time (+03:00)."""
    return to_saudi_time(dt).isoformat()


def get_saudi_partition_date(dt: datetime | None = None) -> datetime:
    """Get the partition date aligned with Saudi Arabia operational business calendar day."""
    target_dt = dt or saudi_now()
    return to_saudi_time(target_dt)

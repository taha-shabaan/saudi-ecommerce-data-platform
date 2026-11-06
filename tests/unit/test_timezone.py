"""Unit tests for Saudi Arabia timezone (Asia/Riyadh / AST) utilities and partition alignment."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from src.common.config import settings
from src.common.s3_client import S3Client
from src.common.timezone import (
    SAUDI_TIMEZONE,
    format_ast,
    get_saudi_partition_date,
    saudi_now,
    to_saudi_time,
    to_utc,
    utc_now,
)


def test_saudi_timezone_constants():
    """Verify SAUDI_TIMEZONE resolves to Asia/Riyadh with +03:00 fixed offset."""
    assert SAUDI_TIMEZONE == ZoneInfo("Asia/Riyadh")
    assert settings.default_timezone == "Asia/Riyadh"

    # AST is always UTC+3 (no daylight saving time)
    sample_dt = datetime(2026, 6, 15, 12, 0, 0, tzinfo=SAUDI_TIMEZONE)
    assert sample_dt.utcoffset() == timedelta(hours=3)


def test_saudi_now_and_utc_now():
    """Verify saudi_now and utc_now return timezone-aware timestamps with correct offsets."""
    s_now = saudi_now()
    u_now = utc_now()
    assert s_now.tzinfo == SAUDI_TIMEZONE
    assert u_now.tzinfo == UTC
    diff = abs((to_utc(s_now) - u_now).total_seconds())
    assert diff < 2.0


def test_to_saudi_time_conversion():
    """Verify conversion of UTC and naive timestamps to Asia/Riyadh."""
    # 21:00 UTC on Oct 27 is 00:00 AST on Oct 28
    utc_dt = datetime(2026, 10, 27, 21, 0, 0, tzinfo=UTC)
    ast_dt = to_saudi_time(utc_dt)

    assert ast_dt.tzinfo == SAUDI_TIMEZONE
    assert ast_dt.year == 2026
    assert ast_dt.month == 10
    assert ast_dt.day == 28
    assert ast_dt.hour == 0
    assert ast_dt.minute == 0


def test_to_utc_conversion():
    """Verify conversion of Asia/Riyadh timestamps to UTC."""
    # 03:00 AST on Oct 28 is 00:00 UTC on Oct 28
    ast_dt = datetime(2026, 10, 28, 3, 0, 0, tzinfo=SAUDI_TIMEZONE)
    utc_dt = to_utc(ast_dt)

    assert utc_dt.tzinfo == UTC
    assert utc_dt.year == 2026
    assert utc_dt.month == 10
    assert utc_dt.day == 28
    assert utc_dt.hour == 0


def test_format_ast():
    """Verify ISO-8601 formatting with AST offset (+03:00)."""
    utc_dt = datetime(2026, 10, 28, 9, 30, 0, tzinfo=UTC)
    ast_str = format_ast(utc_dt)
    assert ast_str == "2026-10-28T12:30:00+03:00"


def test_get_saudi_partition_date_aligns_with_business_day():
    """Verify partition date calculation aligns with Saudi business calendar day."""
    # Late night UTC (22:30 UTC on Oct 27) corresponds to next business day in Riyadh (01:30 AST on Oct 28)
    utc_late = datetime(2026, 10, 27, 22, 30, 0, tzinfo=UTC)
    saudi_dt = get_saudi_partition_date(utc_late)

    assert saudi_dt.day == 28
    assert saudi_dt.month == 10
    assert saudi_dt.year == 2026


def test_s3_partition_keys_use_saudi_time():
    """Verify S3Client partition paths reflect Saudi Arabia operational date."""
    client = S3Client(bucket_name="test-bucket", region_name="eu-west-1")

    # 22:00 UTC on Oct 27 is 01:00 AST on Oct 28
    late_utc = datetime(2026, 10, 27, 22, 0, 0, tzinfo=UTC)
    key = client.build_partition_key(
        source="logistics",
        entity="shipments",
        filename="batch.parquet",
        partition_date=late_utc,
    )

    # Must partition under day=28 (Saudi Arabia business day)
    assert key == "raw/logistics/shipments/year=2026/month=10/day=28/batch.parquet"

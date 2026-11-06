"""Unit tests for Saudi Arabia timezone (Asia/Riyadh / AST) utilities and partition alignment."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.common.config import settings
from src.common.s3_client import S3Client
from src.common.timezone import (
    SAUDI_TIMEZONE,
    format_ast,
    get_saudi_partition_date,
    saudi_now,
    to_saudi_time,
)


def test_saudi_timezone_constants():
    """Verify SAUDI_TIMEZONE resolves to Asia/Riyadh with +03:00 fixed offset."""
    assert SAUDI_TIMEZONE == ZoneInfo("Asia/Riyadh")
    assert settings.default_timezone == "Asia/Riyadh"

    # AST is always UTC+3 (no daylight saving time)
    sample_dt = datetime(2026, 6, 15, 12, 0, 0, tzinfo=SAUDI_TIMEZONE)
    assert sample_dt.utcoffset() == timedelta(hours=3)


def test_saudi_now():
    """Verify saudi_now returns timezone-aware timestamps with Asia/Riyadh timezone."""
    now_ast = saudi_now()
    assert now_ast.tzinfo == SAUDI_TIMEZONE
    assert now_ast.utcoffset() == timedelta(hours=3)


def test_to_saudi_time_conversion():
    """Verify conversion of timestamps to Asia/Riyadh timezone."""
    # Naive timestamp assumes Saudi time by default
    naive_dt = datetime(2026, 10, 28, 14, 30, 0)
    ast_from_naive = to_saudi_time(naive_dt)
    assert ast_from_naive.tzinfo == SAUDI_TIMEZONE
    assert ast_from_naive.hour == 14
    assert ast_from_naive.minute == 30

    # Aware timestamp in another timezone converts accurately to Saudi time
    dubai_tz = ZoneInfo("Asia/Dubai")  # Fixed GST (UTC+4, 1 hour ahead of Riyadh)
    dubai_dt = datetime(2026, 10, 28, 12, 0, 0, tzinfo=dubai_tz)
    ast_from_aware = to_saudi_time(dubai_dt)
    assert ast_from_aware.tzinfo == SAUDI_TIMEZONE
    assert ast_from_aware.hour == 11


def test_format_ast():
    """Verify ISO-8601 formatting with AST offset (+03:00)."""
    ast_dt = datetime(2026, 10, 28, 12, 30, 0, tzinfo=SAUDI_TIMEZONE)
    ast_str = format_ast(ast_dt)
    assert ast_str == "2026-10-28T12:30:00+03:00"


def test_get_saudi_partition_date_aligns_with_business_day():
    """Verify partition date calculation aligns with Saudi business calendar day."""
    ast_dt = datetime(2026, 10, 28, 1, 30, 0, tzinfo=SAUDI_TIMEZONE)
    saudi_dt = get_saudi_partition_date(ast_dt)

    assert saudi_dt.tzinfo == SAUDI_TIMEZONE
    assert saudi_dt.day == 28
    assert saudi_dt.month == 10
    assert saudi_dt.year == 2026


def test_s3_partition_keys_use_saudi_time():
    """Verify S3Client partition paths reflect Saudi Arabia operational date."""
    client = S3Client(bucket_name="test-bucket", region_name="eu-west-1")

    ast_dt = datetime(2026, 10, 28, 1, 0, 0, tzinfo=SAUDI_TIMEZONE)
    key = client.build_partition_key(
        source="logistics",
        entity="shipments",
        filename="batch.parquet",
        partition_date=ast_dt,
    )

    # Must partition under day=28 (Saudi Arabia business day)
    assert key == "raw/logistics/shipments/year=2026/month=10/day=28/batch.parquet"

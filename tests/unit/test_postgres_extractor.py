"""Unit tests for relational high-watermark extractor and watermark state store."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

from src.common.exceptions import PermanentError, TransientError
from src.ingestion.postgres_extractor import (
    ExtractionResult,
    InMemoryWatermarkStore,
    JsonFileWatermarkStore,
    PostgresExtractor,
)


@pytest.fixture
def in_memory_db():
    """Create a temporary SQLite in-memory database simulating PostgreSQL OLTP tables."""
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(
            text("""
            CREATE TABLE customers (
                customer_id TEXT PRIMARY KEY,
                name_ar TEXT NOT NULL,
                name_en TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                region_ar TEXT NOT NULL,
                region_en TEXT NOT NULL,
                city_en TEXT NOT NULL,
                national_address TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            );
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE orders (
                order_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                subtotal_halalas INTEGER NOT NULL,
                vat_halalas INTEGER NOT NULL,
                discount_halalas INTEGER NOT NULL,
                shipping_fee_halalas INTEGER NOT NULL,
                total_halalas INTEGER NOT NULL,
                coupon_code TEXT,
                payment_method TEXT NOT NULL,
                status TEXT NOT NULL,
                shipping_city TEXT NOT NULL,
                shipping_region TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            );
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE order_items (
                order_item_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price_halalas INTEGER NOT NULL,
                unit_cost_halalas INTEGER NOT NULL,
                total_item_halalas INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL
            );
        """)
        )

        # Seed sample rows across different timestamps
        base_time = datetime(2026, 10, 28, 10, 0, 0, tzinfo=UTC)
        conn.execute(
            text("""
            INSERT INTO customers VALUES
            ('CUST-1', 'فهد العتيبي', 'Fahad', 'fahad@test.sa', '+966501112233', 'الرياض', 'Riyadh Region', 'Riyadh', 'Address 1', :t1, :t1),
            ('CUST-2', 'نورة الدوسري', 'Noura', 'noura@test.sa', '+966504445566', 'الشرقية', 'Eastern Province', 'Dammam', 'Address 2', :t2, :t2);
        """),
            {"t1": base_time.isoformat(), "t2": (base_time + timedelta(hours=2)).isoformat()},
        )

        conn.execute(
            text("""
            INSERT INTO orders VALUES
            ('ORD-1', 'CUST-1', 10000, 1500, 0, 2000, 13500, NULL, 'MADA', 'DELIVERED', 'Riyadh', 'Riyadh Region', :t1, :t1),
            ('ORD-2', 'CUST-2', 20000, 3000, 500, 2000, 24500, 'DISC', 'APPLE_PAY', 'PROCESSING', 'Dammam', 'Eastern Province', :t2, :t2);
        """),
            {"t1": base_time.isoformat(), "t2": (base_time + timedelta(hours=2)).isoformat()},
        )

        conn.execute(
            text("""
            INSERT INTO order_items VALUES
            ('ITEM-1', 'ORD-1', 'PROD-1', 1, 10000, 7000, 10000, :t1),
            ('ITEM-2', 'ORD-2', 'PROD-2', 2, 10000, 6000, 20000, :t2);
        """),
            {"t1": base_time.isoformat(), "t2": (base_time + timedelta(hours=2)).isoformat()},
        )
        conn.commit()

    return engine


class MockS3Client:
    """Mock S3 client recording uploads without hitting AWS."""

    def __init__(self):
        self.uploads = []

    def upload_records(self, records, source, entity, file_format="parquet", zone="raw", partition_date=None, **kwargs):
        ext = "parquet" if file_format.lower() == "parquet" else "json.gz"
        key = f"{zone}/{source}/{entity}/year=2026/month=10/day=28/{entity}_test.{ext}"
        self.uploads.append({"key": key, "records": records, "format": file_format})
        return key

    def upload_parquet_records(self, records, source, entity, zone="raw", partition_date=None, **kwargs):
        return self.upload_records(records, source, entity, file_format="parquet", zone=zone, partition_date=partition_date, **kwargs)

    def upload_json_records(self, records, source, entity, zone="raw", partition_date=None, **kwargs):
        return self.upload_records(records, source, entity, file_format="json", zone=zone, partition_date=partition_date, **kwargs)


def test_in_memory_watermark_store():
    """Verify watermark store initializes, reads, and advances timestamps per entity."""
    store = InMemoryWatermarkStore(default_watermark=datetime(2026, 1, 1, tzinfo=UTC))
    assert store.get_watermark("orders") == datetime(2026, 1, 1, tzinfo=UTC)

    new_ts = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
    store.update_watermark("orders", new_ts)
    assert store.get_watermark("orders") == new_ts
    assert store.get_watermark("customers") == datetime(2026, 1, 1, tzinfo=UTC)


def test_json_file_watermark_store(tmp_path):
    """Verify JSON file persistence across instantiations."""
    state_file = tmp_path / "watermarks.json"
    store1 = JsonFileWatermarkStore(file_path=state_file, default_watermark=datetime(2026, 1, 1, tzinfo=UTC))
    store1.update_watermark("orders", datetime(2026, 10, 28, 15, 0, 0, tzinfo=UTC))

    # Second instance reading from same file
    store2 = JsonFileWatermarkStore(file_path=state_file)
    assert store2.get_watermark("orders") == datetime(2026, 10, 28, 15, 0, 0, tzinfo=UTC)


def test_postgres_extractor_incremental_query(in_memory_db):
    """Verify extractor queries only rows within [start_watermark, end_watermark)."""
    mock_s3 = MockS3Client()
    watermark_store = InMemoryWatermarkStore(default_watermark=datetime(2026, 10, 28, 9, 0, 0, tzinfo=UTC))

    extractor = PostgresExtractor(
        engine=in_memory_db,
        s3_client=mock_s3,
        watermark_store=watermark_store,
    )

    # First window: from 09:00 to 11:00 (should match only CUST-1 / ORD-1)
    end_window_1 = datetime(2026, 10, 28, 11, 0, 0, tzinfo=UTC)
    res_orders = extractor.extract_entity("orders", end_watermark=end_window_1)

    assert isinstance(res_orders, ExtractionResult)
    assert res_orders.record_count == 1
    assert res_orders.s3_key is not None
    assert watermark_store.get_watermark("orders") == end_window_1

    # Second window: from 11:00 to 13:00 (should match ORD-2)
    end_window_2 = datetime(2026, 10, 28, 13, 0, 0, tzinfo=UTC)
    res_orders_2 = extractor.extract_entity("orders", end_watermark=end_window_2)
    assert res_orders_2.record_count == 1
    assert watermark_store.get_watermark("orders") == end_window_2

    # Third window: from 13:00 to 15:00 (no new rows)
    end_window_3 = datetime(2026, 10, 28, 15, 0, 0, tzinfo=UTC)
    res_orders_3 = extractor.extract_entity("orders", end_watermark=end_window_3)
    assert res_orders_3.record_count == 0
    assert res_orders_3.s3_key is None
    # Watermark should still advance to end_window_3 to prevent re-scanning empty ranges
    assert watermark_store.get_watermark("orders") == end_window_3


def test_postgres_extractor_order_items_joining_orders(in_memory_db):
    """Verify order_items extraction joins orders on updated_at window."""
    mock_s3 = MockS3Client()
    watermark_store = InMemoryWatermarkStore(default_watermark=datetime(2026, 10, 28, 9, 0, 0, tzinfo=UTC))

    extractor = PostgresExtractor(
        engine=in_memory_db,
        s3_client=mock_s3,
        watermark_store=watermark_store,
    )

    end_window = datetime(2026, 10, 28, 11, 0, 0, tzinfo=UTC)
    res_items = extractor.extract_entity("order_items", end_watermark=end_window)

    assert res_items.record_count == 1
    assert mock_s3.uploads[-1]["records"][0]["order_item_id"] == "ITEM-1"


def test_postgres_extractor_unknown_entity_raises(in_memory_db):
    """Unsupported entity raises PermanentError."""
    extractor = PostgresExtractor(engine=in_memory_db, s3_client=MockS3Client())
    with pytest.raises(PermanentError, match="Unsupported extraction entity"):
        extractor.extract_entity("unsupported_table")


def test_live_postgres_container_extraction():
    """Verify extraction against real PostgreSQL container if running."""
    try:
        from sqlalchemy.exc import SQLAlchemyError

        from src.common.config import settings

        test_engine = create_engine(settings.postgres_connection_url)
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except (OSError, SQLAlchemyError):
        pytest.skip("Local PostgreSQL container not reachable")

    mock_s3 = MockS3Client()
    store = InMemoryWatermarkStore(default_watermark=datetime(2020, 1, 1, tzinfo=UTC))
    extractor = PostgresExtractor(
        engine=test_engine,
        s3_client=mock_s3,
        watermark_store=store,
    )

    results = extractor.extract_all()
    assert "customers" in results
    assert "orders" in results
    assert results["customers"].record_count >= 100
    assert results["orders"].record_count >= 500
    assert len(mock_s3.uploads) == 4


def test_backfill_mode_does_not_mutate_watermark(in_memory_db):
    """Verify that is_backfill=True extracts historical data without altering stored high-watermark."""
    mock_s3 = MockS3Client()
    current_stored = datetime(2026, 10, 28, 18, 0, 0, tzinfo=UTC)
    watermark_store = InMemoryWatermarkStore(default_watermark=current_stored)
    watermark_store.update_watermark("orders", current_stored)

    extractor = PostgresExtractor(
        engine=in_memory_db,
        s3_client=mock_s3,
        watermark_store=watermark_store,
    )

    # Historical backfill window (earlier than current stored watermark)
    backfill_start = datetime(2026, 10, 28, 9, 0, 0, tzinfo=UTC)
    backfill_end = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
    result = extractor.extract_entity(
        "orders",
        start_watermark=backfill_start,
        end_watermark=backfill_end,
        is_backfill=True,
    )

    assert result.record_count >= 1
    # Watermark must remain at 18:00:00, not regressed to 12:00:00
    assert watermark_store.get_watermark("orders") == current_stored


def test_watermark_regression_guard_on_earlier_end_watermark(in_memory_db):
    """Verify stored watermark does not regress even if is_backfill is not explicitly passed."""
    mock_s3 = MockS3Client()
    current_stored = datetime(2026, 10, 28, 18, 0, 0, tzinfo=UTC)
    watermark_store = InMemoryWatermarkStore(default_watermark=current_stored)
    watermark_store.update_watermark("orders", current_stored)

    extractor = PostgresExtractor(
        engine=in_memory_db,
        s3_client=mock_s3,
        watermark_store=watermark_store,
    )

    earlier_end = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
    extractor.extract_entity("orders", end_watermark=earlier_end)
    assert watermark_store.get_watermark("orders") == current_stored


def test_parquet_timestamp_native_datetime_retained(in_memory_db):
    """Verify Parquet extraction retains native datetime objects, while JSON stringifies."""
    mock_s3 = MockS3Client()
    store = InMemoryWatermarkStore(default_watermark=datetime(2026, 10, 28, 9, 0, 0, tzinfo=UTC))
    extractor = PostgresExtractor(engine=in_memory_db, s3_client=mock_s3, watermark_store=store)

    # 1. Parquet extraction
    extractor.extract_entity("orders", file_format="parquet", end_watermark=datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC))
    parquet_records = mock_s3.uploads[-1]["records"]
    assert len(parquet_records) >= 1
    created_at_val = parquet_records[0]["created_at"]
    # Must be native datetime instance, not string
    assert isinstance(created_at_val, datetime)

    # 2. JSON extraction (reset watermark to 09:00 for test)
    store.update_watermark("orders", datetime(2026, 10, 28, 9, 0, 0, tzinfo=UTC))
    extractor.extract_entity("orders", file_format="json", end_watermark=datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC))
    json_records = mock_s3.uploads[-1]["records"]
    assert isinstance(json_records[0]["created_at"], str)


def test_transient_database_error_retry_and_escalation():
    """Verify extractor catches operational DB errors, retries with backoff, and escalates to TransientError."""
    failing_engine = MagicMock()
    # Mock connect to raise OperationalError
    failing_engine.connect.side_effect = OperationalError("connection refused", params=None, orig=Exception("timeout"))
    failing_engine.dialect.name = "postgresql"

    extractor = PostgresExtractor(engine=failing_engine, s3_client=MockS3Client())

    with pytest.raises(TransientError) as exc_info:
        extractor._execute_query_with_retry(
            query_sql="SELECT 1",
            params={},
            id_correlation="test_corr_123",
            max_attempts=2,
            base_wait_seconds=0.01,
        )

    assert exc_info.value.error_code == "DATABASE_TRANSIENT_FAILURE"
    assert failing_engine.connect.call_count == 2


def test_programming_error_raises_permanent_error():
    """Verify SQL syntax or schema mismatch errors raise PermanentError immediately without retrying."""
    failing_engine = MagicMock()
    failing_engine.connect.side_effect = ProgrammingError("syntax error in SQL", params=None, orig=Exception("syntax"))
    failing_engine.dialect.name = "postgresql"

    extractor = PostgresExtractor(engine=failing_engine, s3_client=MockS3Client())

    with pytest.raises(PermanentError) as exc_info:
        extractor._execute_query_with_retry(
            query_sql="INVALID SQL SYNTAX",
            params={},
            id_correlation="test_corr_syntax",
            max_attempts=3,
        )

    assert exc_info.value.error_code == "SQL_SYNTAX_OR_SCHEMA_ERROR"
    # PermanentError must not retry!
    assert failing_engine.connect.call_count == 1

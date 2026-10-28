"""Unit tests for relational high-watermark extractor and watermark state store."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text

from src.common.exceptions import PermanentError
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

    def upload_parquet_records(self, records, source, entity, zone="raw", partition_date=None, **kwargs):
        key = f"{zone}/{source}/{entity}/year=2026/month=10/day=28/{entity}_test.parquet"
        self.uploads.append({"key": key, "records": records, "format": "parquet"})
        return key

    def upload_json_records(self, records, source, entity, zone="raw", partition_date=None, **kwargs):
        key = f"{zone}/{source}/{entity}/year=2026/month=10/day=28/{entity}_test.json.gz"
        self.uploads.append({"key": key, "records": records, "format": "json.gz"})
        return key


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

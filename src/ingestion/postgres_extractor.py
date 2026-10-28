"""Relational High-Watermark Extractor for PostgreSQL OLTP Store.

Extracts incremental change batches from PostgreSQL (customers, products, orders, order_items)
based on high-watermark timestamps, landing immutable partitioned artifacts into the AWS S3 Raw Zone.
"""

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from sqlalchemy import Engine, create_engine, text

from src.common.config import settings
from src.common.exceptions import PermanentError
from src.common.logging import generate_correlation_id, get_logger
from src.common.s3_client import S3Client

logger = get_logger("postgres_extractor")


class WatermarkStore(ABC):
    """Abstract interface managing persistent high-watermark state."""

    @abstractmethod
    def get_watermark(self, entity: str) -> datetime:
        """Retrieve current high-watermark timestamp for an entity."""

    @abstractmethod
    def update_watermark(self, entity: str, watermark: datetime) -> None:
        """Persist advanced high-watermark timestamp for an entity."""


class InMemoryWatermarkStore(WatermarkStore):
    """In-memory watermark store primarily used for isolated unit testing."""

    def __init__(self, default_watermark: datetime | None = None) -> None:
        self.default_watermark = default_watermark or datetime(2026, 1, 1, tzinfo=UTC)
        self._watermarks: dict[str, datetime] = {}

    def get_watermark(self, entity: str) -> datetime:
        return self._watermarks.get(entity, self.default_watermark)

    def update_watermark(self, entity: str, watermark: datetime) -> None:
        self._watermarks[entity] = watermark


class JsonFileWatermarkStore(WatermarkStore):
    """Durable file-based watermark store persisting JSON timestamps."""

    def __init__(
        self,
        file_path: str | Path = "metadata/postgres_watermarks.json",
        default_watermark: datetime | None = None,
    ) -> None:
        self.file_path = Path(file_path)
        self.default_watermark = default_watermark or datetime(2026, 1, 1, tzinfo=UTC)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_data(self) -> dict[str, str]:
        if not self.file_path.exists():
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Could not read watermark file {self.file_path}: {e}")
            return {}

    def get_watermark(self, entity: str) -> datetime:
        data = self._load_data()
        ts_str = data.get(entity)
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str)
                return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
            except ValueError:
                pass
        return self.default_watermark

    def update_watermark(self, entity: str, watermark: datetime) -> None:
        data = self._load_data()
        data[entity] = watermark.isoformat()
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


@dataclass
class ExtractionResult:
    """Metadata and execution metrics for an entity extraction batch."""

    entity: str
    record_count: int
    start_watermark: datetime
    end_watermark: datetime
    s3_key: str | None
    duration_ms: int
    id_correlation: str


class PostgresExtractor:
    """Enterprise relational extractor pulling incremental batches from PostgreSQL into S3 Raw Zone."""

    # Entities with direct updated_at column
    DIRECT_WATERMARK_QUERIES: ClassVar[dict[str, str]] = {
        "customers": """
            SELECT customer_id, name_ar, name_en, email, phone, region_ar, region_en,
                   city_en, national_address, created_at, updated_at
            FROM customers
            WHERE updated_at >= :start_watermark AND updated_at < :end_watermark
            ORDER BY updated_at ASC
        """,
        "products": """
            SELECT product_id, name_ar, name_en, category, unit_price_halalas, unit_cost_halalas,
                   created_at, updated_at
            FROM products
            WHERE updated_at >= :start_watermark AND updated_at < :end_watermark
            ORDER BY updated_at ASC
        """,
        "orders": """
            SELECT order_id, customer_id, subtotal_halalas, vat_halalas, discount_halalas,
                   shipping_fee_halalas, total_halalas, coupon_code, payment_method, status,
                   shipping_city, shipping_region, created_at, updated_at
            FROM orders
            WHERE updated_at >= :start_watermark AND updated_at < :end_watermark
            ORDER BY updated_at ASC
        """,
    }

    # order_items links to orders to capture lines of updated orders
    JOIN_WATERMARK_QUERIES: ClassVar[dict[str, str]] = {
        "order_items": """
            SELECT oi.order_item_id, oi.order_id, oi.product_id, oi.quantity,
                   oi.unit_price_halalas, oi.unit_cost_halalas, oi.total_item_halalas,
                   oi.created_at
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            WHERE o.updated_at >= :start_watermark AND o.updated_at < :end_watermark
            ORDER BY o.updated_at ASC, oi.order_item_id ASC
        """
    }

    def __init__(
        self,
        engine: Engine | None = None,
        db_url: str | None = None,
        s3_client: S3Client | None = None,
        watermark_store: WatermarkStore | None = None,
    ) -> None:
        if engine:
            self.engine = engine
        else:
            url = db_url or settings.postgres_connection_url
            self.engine = create_engine(url, pool_pre_ping=True)

        self.s3_client = s3_client or S3Client()
        self.watermark_store = watermark_store or JsonFileWatermarkStore()

    def extract_entity(
        self,
        entity: str,
        start_watermark: datetime | None = None,
        end_watermark: datetime | None = None,
        zone: str = "raw",
        file_format: str = "parquet",
        id_correlation: str | None = None,
    ) -> ExtractionResult:
        """Extract a single entity within [start_watermark, end_watermark) and land in S3."""
        clean_entity = entity.strip().lower()
        query_sql = self.DIRECT_WATERMARK_QUERIES.get(clean_entity) or self.JOIN_WATERMARK_QUERIES.get(clean_entity)
        if not query_sql:
            raise PermanentError(
                message=f"Unsupported extraction entity '{entity}'",
                error_code="UNSUPPORTED_ENTITY_ERROR",
                id_correlation=id_correlation,
                context={"supported_entities": list(self.DIRECT_WATERMARK_QUERIES.keys()) + list(self.JOIN_WATERMARK_QUERIES.keys())},
            )

        correlation_id = id_correlation or generate_correlation_id(f"pg_extract_{clean_entity}")
        start_ts = start_watermark or self.watermark_store.get_watermark(clean_entity)
        end_ts = end_watermark or datetime.now(UTC)

        start_time = time.time()
        logger.info(
            f"Starting incremental extraction for '{clean_entity}' from {start_ts.isoformat()} to {end_ts.isoformat()}",
            extra={"id_correlation": correlation_id, "entity": clean_entity},
        )

        records: list[dict[str, Any]] = []
        with self.engine.connect() as conn:
            result = conn.execute(
                text(query_sql),
                {
                    "start_watermark": start_ts.isoformat() if "sqlite" in self.engine.dialect.name else start_ts,
                    "end_watermark": end_ts.isoformat() if "sqlite" in self.engine.dialect.name else end_ts,
                },
            )
            columns = list(result.keys())
            for row in result.fetchall():
                row_dict = {}
                for col_name, val in zip(columns, row):
                    if isinstance(val, datetime):
                        row_dict[col_name] = val.isoformat()
                    else:
                        row_dict[col_name] = val
                records.append(row_dict)

        s3_key: str | None = None
        if records:
            if file_format.lower() == "parquet":
                s3_key = self.s3_client.upload_parquet_records(
                    records=records,
                    source="postgres",
                    entity=clean_entity,
                    zone=zone,
                    partition_date=end_ts,
                    filename_prefix=f"{clean_entity}_extract",
                    id_correlation=correlation_id,
                )
            else:
                s3_key = self.s3_client.upload_json_records(
                    records=records,
                    source="postgres",
                    entity=clean_entity,
                    zone=zone,
                    partition_date=end_ts,
                    filename_prefix=f"{clean_entity}_extract",
                    id_correlation=correlation_id,
                )

        # Advance watermark store to end_ts
        self.watermark_store.update_watermark(clean_entity, end_ts)
        duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"Extraction completed for '{clean_entity}': {len(records)} records extracted in {duration_ms}ms.",
            extra={
                "id_correlation": correlation_id,
                "duration_ms": duration_ms,
                "entity": clean_entity,
                "record_count": len(records),
                "s3_key": s3_key,
            },
        )

        return ExtractionResult(
            entity=clean_entity,
            record_count=len(records),
            start_watermark=start_ts,
            end_watermark=end_ts,
            s3_key=s3_key,
            duration_ms=duration_ms,
            id_correlation=correlation_id,
        )

    def extract_all(
        self,
        entities: list[str] | None = None,
        end_watermark: datetime | None = None,
        zone: str = "raw",
        file_format: str = "parquet",
        id_correlation: str | None = None,
    ) -> dict[str, ExtractionResult]:
        """Extract all target entities in topological order."""
        target_entities = entities or ["customers", "products", "orders", "order_items"]
        results = {}
        for ent in target_entities:
            results[ent] = self.extract_entity(
                entity=ent,
                end_watermark=end_watermark,
                zone=zone,
                file_format=file_format,
                id_correlation=id_correlation,
            )
        return results


if __name__ == "__main__":
    extractor = PostgresExtractor()
    logger.info("Executing test extraction of all PostgreSQL entities...")
    extraction_results = extractor.extract_all()
    for ent_name, res in extraction_results.items():
        print(f"[{ent_name}] Extracted {res.record_count} records -> S3: {res.s3_key}")

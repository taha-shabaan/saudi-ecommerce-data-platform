"""Relational High-Watermark Extractor for PostgreSQL OLTP Store.

Extracts incremental change batches from PostgreSQL (customers, products, orders, order_items)
based on high-watermark timestamps, landing immutable partitioned artifacts into the AWS S3 Raw Zone.
"""

import json
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, cast

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import (
    DatabaseError,
    OperationalError,
    ProgrammingError,
    SQLAlchemyError,
)

from src.common.config import settings
from src.common.exceptions import PermanentError, TransientError
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
                data = json.load(f)
                return cast(dict[str, str], data) if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as err:
            logger.warning(
                f"Could not read watermark file {self.file_path}: {err}. Returning empty state.",
                extra={"file_path": str(self.file_path)},
            )
            return {}

    def get_watermark(self, entity: str) -> datetime:
        data = self._load_data()
        ts_str = data.get(entity)
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str)
                return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
            except ValueError as err:
                logger.warning(
                    f"Corrupted timestamp string '{ts_str}' for entity '{entity}': {err}. Reverting to default watermark.",
                    extra={"entity": entity, "corrupted_timestamp": ts_str},
                )
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

    def _execute_query_with_retry(
        self,
        query_sql: str,
        params: dict[str, Any],
        id_correlation: str,
        max_attempts: int = 3,
        base_wait_seconds: float = 1.0,
    ) -> list[dict[str, Any]]:
        """Execute a query against PostgreSQL with exponential backoff on transient errors."""
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                with self.engine.connect() as conn:
                    result = conn.execute(text(query_sql), params)
                    columns = list(result.keys())
                    rows = result.fetchall()
                    records: list[dict[str, Any]] = []
                    for row in rows:
                        row_dict = {}
                        for col_name, val in zip(columns, row):
                            row_dict[col_name] = val
                        records.append(row_dict)
                    return records
            except ProgrammingError as err:
                raise PermanentError(
                    message=f"Permanent SQL error executing extraction: {err}",
                    error_code="SQL_SYNTAX_OR_SCHEMA_ERROR",
                    id_correlation=id_correlation,
                    context={"sql": query_sql, "error": str(err)},
                ) from err
            except (OperationalError, DatabaseError, SQLAlchemyError) as err:
                last_error = err
                if attempt == max_attempts:
                    logger.error(
                        f"Database query failed after {max_attempts} attempts: {err}",
                        extra={"id_correlation": id_correlation, "attempt": attempt},
                    )
                    break
                wait_time = min(base_wait_seconds * (2 ** (attempt - 1)) + random.uniform(0, 0.2), 30.0)
                logger.warning(
                    f"Transient database error on attempt {attempt}/{max_attempts}: {err}. Retrying in {wait_time:.2f}s...",
                    extra={"id_correlation": id_correlation, "attempt": attempt, "wait_seconds": wait_time},
                )
                time.sleep(wait_time)

        raise TransientError(
            message=f"Database extraction failed after {max_attempts} attempts: {last_error}",
            error_code="DATABASE_TRANSIENT_FAILURE",
            id_correlation=id_correlation,
            context={"sql": query_sql, "error": str(last_error)},
        ) from last_error

    def extract_entity(
        self,
        entity: str,
        start_watermark: datetime | None = None,
        end_watermark: datetime | None = None,
        zone: str = "raw",
        file_format: str = "parquet",
        is_backfill: bool = False,
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
            f"Starting incremental extraction for '{clean_entity}' from {start_ts.isoformat()} to {end_ts.isoformat()}"
            + (" (BACKFILL)" if is_backfill else ""),
            extra={"id_correlation": correlation_id, "entity": clean_entity, "is_backfill": is_backfill},
        )

        raw_rows = self._execute_query_with_retry(
            query_sql=query_sql,
            params={
                "start_watermark": start_ts.isoformat() if "sqlite" in self.engine.dialect.name else start_ts,
                "end_watermark": end_ts.isoformat() if "sqlite" in self.engine.dialect.name else end_ts,
            },
            id_correlation=correlation_id,
        )

        records: list[dict[str, Any]] = []
        is_json_format = file_format.lower() in ("json", "json.gz")
        for row in raw_rows:
            row_dict: dict[str, Any] = {}
            for col_name, val in row.items():
                if isinstance(val, datetime):
                    if is_json_format:
                        row_dict[col_name] = val.isoformat()
                    else:
                        row_dict[col_name] = val if val.tzinfo else val.replace(tzinfo=UTC)
                elif isinstance(val, str) and not is_json_format and col_name.endswith(("_at", "_date", "_time", "timestamp")):
                    try:
                        parsed_dt = datetime.fromisoformat(val)
                        row_dict[col_name] = parsed_dt if parsed_dt.tzinfo else parsed_dt.replace(tzinfo=UTC)
                    except ValueError:
                        row_dict[col_name] = val
                else:
                    row_dict[col_name] = val
            records.append(row_dict)

        s3_key: str | None = None
        if records:
            s3_key = self.s3_client.upload_records(
                records=records,
                source="postgres",
                entity=clean_entity,
                file_format=file_format,
                zone=zone,
                partition_date=end_ts,
                filename_prefix=f"{clean_entity}_extract",
                id_correlation=correlation_id,
            )

        # Advance watermark store only if not in backfill mode and end_ts is strictly forward
        current_watermark = self.watermark_store.get_watermark(clean_entity)
        if not is_backfill and end_ts > current_watermark:
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
                "is_backfill": is_backfill,
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
        is_backfill: bool = False,
        id_correlation: str | None = None,
    ) -> dict[str, ExtractionResult]:
        """Extract all target entities in topological order."""
        target_entities = entities or ["customers", "products", "orders", "order_items"]
        results: dict[str, ExtractionResult] = {}
        for entity_name in target_entities:
            results[entity_name] = self.extract_entity(
                entity=entity_name,
                end_watermark=end_watermark,
                zone=zone,
                file_format=file_format,
                is_backfill=is_backfill,
                id_correlation=id_correlation,
            )
        return results


if __name__ == "__main__":
    extractor = PostgresExtractor()
    logger.info("Executing test extraction of all PostgreSQL entities...")
    extraction_results = extractor.extract_all()
    for entity_name, result in extraction_results.items():
        print(f"[{entity_name}] Extracted {result.record_count} records -> S3: {result.s3_key}")

"""AWS S3 Storage Client and Raw Zone Partitioning Manager.

Provides a robust, production-grade interface for landing data into AWS S3 (or MinIO):
- Enforces deterministic Hive-style partition paths:
  `raw/{source}/{entity}/year=YYYY/month=MM/day=DD/{filename}.parquet`
- Primary ingestion option: High-throughput Snappy-compressed Parquet via PyArrow.
- Secondary ingestion option: In-memory gzipped JSON Lines (`.json.gz`) with zero disk bloat.
- Handles retries on transient connection or throttling failures with exponential backoff.
- Tracks execution correlation IDs and structured audit logs conforming to GLOSSARY.md.
"""

import gzip
import io
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import boto3
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError

from src.common.config import settings
from src.common.exceptions import PermanentError, TransientError
from src.common.logging import generate_correlation_id, get_logger

logger = get_logger("s3_client")


class S3Client:
    """Enterprise client managing S3 lakehouse uploads, partitioned storage, and object operations."""

    def __init__(
        self,
        bucket_name: str | None = None,
        region_name: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        self.bucket_name = bucket_name or settings.env_storage_bucket
        self.region_name = region_name or settings.aws_default_region

        session_kwargs: dict[str, Any] = {"region_name": self.region_name}
        key_id = aws_access_key_id or settings.aws_access_key_id
        secret_key = aws_secret_access_key or settings.aws_secret_access_key

        if key_id and secret_key:
            session_kwargs["aws_access_key_id"] = key_id
            session_kwargs["aws_secret_access_key"] = secret_key

        self._s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            **session_kwargs,
        )

    def build_partition_key(
        self,
        source: str,
        entity: str,
        filename: str,
        zone: str = "raw",
        partition_date: datetime | None = None,
    ) -> str:
        """Construct deterministic Hive-style S3 object key.

        Format:
            {zone}/{source}/{entity}/year=YYYY/month=MM/day=DD/{filename}
        """
        dt = partition_date or datetime.now(UTC)
        year = dt.strftime("%Y")
        month = dt.strftime("%m")
        day = dt.strftime("%d")

        zone_clean = zone.strip().lower()
        source_clean = source.strip().lower()
        entity_clean = entity.strip().lower()
        filename_clean = filename.strip()

        return f"{zone_clean}/{source_clean}/{entity_clean}/year={year}/month={month}/day={day}/{filename_clean}"

    def build_raw_partition_key(
        self,
        source: str,
        entity: str,
        filename: str,
        partition_date: datetime | None = None,
    ) -> str:
        """Construct deterministic Hive-style S3 object key for the Raw Zone."""
        return self.build_partition_key(
            source=source,
            entity=entity,
            filename=filename,
            zone="raw",
            partition_date=partition_date,
        )

    def _upload_records(
        self,
        records: list[dict[str, Any]] | Any,
        source: str,
        entity: str,
        extension: str,
        serializer_func: Callable[[Any], bytes],
        content_type: str,
        zone: str = "raw",
        partition_date: datetime | None = None,
        filename_prefix: str | None = None,
        id_correlation: str | None = None,
    ) -> str:
        """Internal DRY upload workflow: validation, path generation, serialization, retry, and audit logging."""
        record_count = len(records) if hasattr(records, "__len__") else 0
        if record_count == 0:
            raise PermanentError(
                message=f"Cannot upload empty record set to S3 for {source}.{entity}",
                error_code="EMPTY_RECORD_SET_ERROR",
                id_correlation=id_correlation,
                context={"source": source, "entity": entity},
            )

        correlation_id = id_correlation or generate_correlation_id("s3_upload")
        dt = partition_date or datetime.now(UTC)
        timestamp_slug = dt.strftime("%Y%m%d_%H%M%S")
        prefix = filename_prefix or f"{entity}_extract"
        filename = f"{prefix}_{timestamp_slug}.{extension}"

        s3_key = self.build_partition_key(
            source=source,
            entity=entity,
            filename=filename,
            zone=zone,
            partition_date=dt,
        )

        payload_bytes = serializer_func(records)
        payload_size_bytes = len(payload_bytes)

        start_time = time.time()
        self._put_object_with_retry(
            key=s3_key,
            body=payload_bytes,
            content_type=content_type,
            metadata={
                "id_correlation": correlation_id,
                "record_count": str(record_count),
                "source": source,
                "entity": entity,
                "format": extension,
            },
        )
        duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"Uploaded {record_count} records ({payload_size_bytes} bytes, {extension}) to s3://{self.bucket_name}/{s3_key}",
            extra={
                "id_correlation": correlation_id,
                "duration_ms": duration_ms,
                "payload": {
                    "bucket": self.bucket_name,
                    "key": s3_key,
                    "records_count": record_count,
                    "bytes": payload_size_bytes,
                    "format": extension,
                },
            },
        )
        return s3_key

    def upload_records(
        self,
        records: list[dict[str, Any]] | Any,
        source: str,
        entity: str,
        file_format: str = "parquet",
        zone: str = "raw",
        partition_date: datetime | None = None,
        filename_prefix: str | None = None,
        id_correlation: str | None = None,
        compression: str = "snappy",
    ) -> str:
        """First-choice upload interface to land datasets into the S3 Data Lake.

        Defaults to columnar Snappy Parquet in the Raw Zone ('raw/').
        """
        clean_format = file_format.strip().lower()
        if clean_format == "parquet":
            return self.upload_parquet_records(
                records=records,
                source=source,
                entity=entity,
                zone=zone,
                partition_date=partition_date,
                filename_prefix=filename_prefix,
                id_correlation=id_correlation,
                compression=compression,
            )
        if clean_format in ("json", "json.gz"):
            return self.upload_json_records(
                records=records,
                source=source,
                entity=entity,
                zone=zone,
                partition_date=partition_date,
                filename_prefix=filename_prefix,
                id_correlation=id_correlation,
            )
        raise PermanentError(
            message=f"Unsupported lake upload format '{file_format}'. Supported formats: 'parquet', 'json'.",
            error_code="UNSUPPORTED_STORAGE_FORMAT",
            id_correlation=id_correlation,
            context={"format": file_format, "source": source, "entity": entity},
        )

    def upload_parquet_records(
        self,
        records: list[dict[str, Any]] | Any,
        source: str,
        entity: str,
        zone: str = "raw",
        partition_date: datetime | None = None,
        filename_prefix: str | None = None,
        id_correlation: str | None = None,
        compression: str = "snappy",
    ) -> str:
        """Primary upload option: serialize records to Snappy-compressed Parquet and upload to S3."""
        def _serialize_parquet(data: Any) -> bytes:
            if isinstance(data, list):
                table = pa.Table.from_pylist(data)
            elif hasattr(data, "to_parquet"):  # pandas DataFrame
                table = pa.Table.from_pandas(data)
            elif isinstance(data, pa.Table):
                table = data
            else:
                table = pa.Table.from_pylist(list(data))

            buffer = io.BytesIO()
            pq.write_table(table, buffer, compression=compression)
            return buffer.getvalue()

        return self._upload_records(
            records=records,
            source=source,
            entity=entity,
            extension="parquet",
            serializer_func=_serialize_parquet,
            content_type="application/vnd.apache.parquet",
            zone=zone,
            partition_date=partition_date,
            filename_prefix=filename_prefix,
            id_correlation=id_correlation,
        )

    def upload_json_records(
        self,
        records: list[dict[str, Any]],
        source: str,
        entity: str,
        zone: str = "raw",
        partition_date: datetime | None = None,
        filename_prefix: str | None = None,
        id_correlation: str | None = None,
    ) -> str:
        """Secondary upload option: serialize records to compressed JSON lines (.json.gz) and upload to S3."""
        def _serialize_json_gz(data: list[dict[str, Any]]) -> bytes:
            buffer = io.BytesIO()
            with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0.0) as gz_out:
                for record in data:
                    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
                    gz_out.write(line.encode("utf-8"))
            return buffer.getvalue()

        return self._upload_records(
            records=records,
            source=source,
            entity=entity,
            extension="json.gz",
            serializer_func=_serialize_json_gz,
            content_type="application/gzip",
            zone=zone,
            partition_date=partition_date,
            filename_prefix=filename_prefix,
            id_correlation=id_correlation,
        )

    def _put_object_with_retry(
        self,
        key: str,
        body: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
        max_attempts: int = 3,
    ) -> None:
        """Execute S3 put_object with exponential backoff on transient errors."""
        attempt = 0
        wait_seconds = 1.0

        while attempt < max_attempts:
            attempt += 1
            try:
                self._s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=key,
                    Body=body,
                    ContentType=content_type,
                    Metadata=metadata or {},
                )
                return
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                # Transient throttling or server errors
                if error_code in ["RequestTimeout", "ThrottlingException", "SlowDown", "503", "500"] and attempt < max_attempts:
                    logger.warning(f"S3 PutObject transient error ({error_code}). Retrying in {wait_seconds}s (Attempt {attempt}/{max_attempts})...")
                    time.sleep(wait_seconds)
                    wait_seconds *= 2.0
                    continue
                raise PermanentError(
                    message=f"Permanent S3 ClientError: {e!s}",
                    error_code="S3_CLIENT_ERROR",
                    context={"bucket": self.bucket_name, "key": key, "s3_code": error_code},
                ) from e
            except (BotoCoreError, OSError) as e:
                if attempt < max_attempts:
                    logger.warning(f"S3 connection error ({e!s}). Retrying in {wait_seconds}s...")
                    time.sleep(wait_seconds)
                    wait_seconds *= 2.0
                    continue
                raise TransientError(
                    message=f"Exhausted S3 retries: {e!s}",
                    error_code="S3_CONNECTION_TIMEOUT",
                    context={"bucket": self.bucket_name, "key": key, "attempts": attempt},
                ) from e

    def object_exists(self, key: str) -> bool:
        """Verify if a specific S3 object key exists via head_object."""
        try:
            self._s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ["404", "NoSuchKey"]:
                return False
            raise PermanentError(f"Error checking object existence for {key}: {e!s}") from e

    def list_objects(self, prefix: str) -> list[str]:
        """List all object keys under a given S3 bucket prefix."""
        keys = []
        paginator = self._s3_client.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                if "Contents" in page:
                    for obj in page["Contents"]:
                        keys.append(obj["Key"])
            return keys
        except ClientError as e:
            raise PermanentError(f"Error listing S3 objects with prefix {prefix}: {e!s}") from e


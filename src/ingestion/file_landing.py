"""Operational & 3PL Logistics File Landing Extractor.

Ingests operational courier tracking spreadsheets (.xlsx), catalog overrides (.csv),
and logistics files (.parquet/.csv), landing immutable extracts into the AWS S3 Raw Zone.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src.common.exceptions import PermanentError
from src.common.logging import generate_correlation_id, get_logger
from src.common.s3_client import S3Client

logger = get_logger("file_landing")


@dataclass
class FileLandingResult:
    """Metadata and execution metrics for a landed operational file."""

    source: str
    entity: str
    file_path: str
    record_count: int
    s3_key: str
    file_format: str
    duration_ms: int
    id_correlation: str


class FileLandingExtractor:
    """Ingests operational and 3PL logistics files into AWS S3 Raw Zone."""

    def __init__(self, s3_client: S3Client | None = None) -> None:
        self.s3_client = s3_client or S3Client()

    def land_file(
        self,
        file_path: Path | str,
        source: str,
        entity: str,
        execution_date: datetime | None = None,
        file_format: str = "parquet",
        sheet_name: str | int | None = None,
        required_columns: list[str] | None = None,
        id_correlation: str | None = None,
    ) -> FileLandingResult:
        """Validate an operational file and land it into the S3 Raw Zone."""
        start_time = time.monotonic()
        path = Path(file_path)
        corr_id = id_correlation or generate_correlation_id()
        exec_date = execution_date or datetime.now(tz=UTC)

        if not path.exists():
            raise PermanentError(
                message=f"Operational file does not exist: {path}",
                error_code="FILE_NOT_FOUND",
                id_correlation=corr_id,
                context={"file_path": str(path), "source": source, "entity": entity},
            )

        if path.stat().st_size == 0:
            raise PermanentError(
                message=f"Operational file is empty (0 bytes): {path}",
                error_code="EMPTY_OPERATIONAL_FILE",
                id_correlation=corr_id,
                context={"file_path": str(path), "source": source, "entity": entity},
            )

        suffix = path.suffix.lower()
        try:
            if suffix == ".parquet":
                df = pd.read_parquet(path)
            elif suffix == ".csv":
                df = pd.read_csv(path)
            elif suffix in (".xlsx", ".xls"):
                raw_excel = pd.read_excel(path, sheet_name=sheet_name if sheet_name is not None else 0)
                if isinstance(raw_excel, dict):
                    first_sheet_name = next(iter(raw_excel.keys()))
                    df = raw_excel[first_sheet_name]
                else:
                    df = raw_excel
            else:
                raise PermanentError(
                    message=f"Unsupported operational file format '{suffix}'. Supported: .parquet, .csv, .xlsx",
                    error_code="UNSUPPORTED_FILE_FORMAT",
                    id_correlation=corr_id,
                    context={"file_path": str(path), "extension": suffix},
                )
        except pd.errors.EmptyDataError:
            raise PermanentError(
                message=f"Operational file contains no columns or data: {path}",
                error_code="EMPTY_OPERATIONAL_FILE",
                id_correlation=corr_id,
                context={"file_path": str(path), "source": source, "entity": entity},
            )

        if len(df) == 0:
            raise PermanentError(
                message=f"Operational file contains zero records: {path}",
                error_code="EMPTY_OPERATIONAL_FILE",
                id_correlation=corr_id,
                context={"file_path": str(path), "source": source, "entity": entity},
            )

        if required_columns:
            missing_cols = [col for col in required_columns if col not in df.columns]
            if missing_cols:
                raise PermanentError(
                    message=f"Operational file {path.name} missing required columns: {missing_cols}",
                    error_code="SCHEMA_VALIDATION_ERROR",
                    id_correlation=corr_id,
                    context={
                        "file_path": str(path),
                        "missing_columns": missing_cols,
                        "present_columns": list(df.columns),
                    },
                )

        records = df.to_dict(orient="records")
        record_count = len(records)

        s3_key = self.s3_client.upload_records(
            records=records,
            source=source,
            entity=entity,
            zone="raw",
            partition_date=exec_date,
            file_format=file_format,
            id_correlation=corr_id,
        )

        duration_ms = int((time.monotonic() - start_time) * 1000)

        logger.info(
            f"Successfully landed {record_count} records from {path.name} to S3 Raw Zone: {s3_key}",
            extra={
                "source": source,
                "entity": entity,
                "record_count": record_count,
                "s3_key": s3_key,
                "duration_ms": duration_ms,
                "id_correlation": corr_id,
            },
        )

        return FileLandingResult(
            source=source,
            entity=entity,
            file_path=str(path),
            record_count=record_count,
            s3_key=s3_key,
            file_format=file_format,
            duration_ms=duration_ms,
            id_correlation=corr_id,
        )

    def land_directory(
        self,
        directory_path: Path | str,
        source: str = "logistics",
        execution_date: datetime | None = None,
        file_format: str = "parquet",
        id_correlation: str | None = None,
    ) -> list[FileLandingResult]:
        """Discover and batch-land all operational files in a folder into S3 Raw Zone."""
        path = Path(directory_path)
        corr_id = id_correlation or generate_correlation_id()
        exec_date = execution_date or datetime.now(tz=UTC)

        if not path.exists() or not path.is_dir():
            raise PermanentError(
                message=f"Directory does not exist or is not a folder: {path}",
                error_code="DIRECTORY_NOT_FOUND",
                id_correlation=corr_id,
                context={"directory_path": str(path), "source": source},
            )

        supported_extensions = {".parquet", ".csv", ".xlsx", ".xls"}
        extension_priority = {".parquet": 1, ".csv": 2, ".xlsx": 3, ".xls": 4}
        best_file_by_stem: dict[str, Path] = {}

        for candidate_file in sorted(path.iterdir()):
            if candidate_file.is_file() and candidate_file.suffix.lower() in supported_extensions:
                stem = candidate_file.stem
                ext = candidate_file.suffix.lower()
                if stem not in best_file_by_stem or extension_priority.get(ext, 99) < extension_priority.get(
                    best_file_by_stem[stem].suffix.lower(), 99
                ):
                    best_file_by_stem[stem] = candidate_file

        results: list[FileLandingResult] = []
        for entity, file_entry in sorted(best_file_by_stem.items()):
            result = self.land_file(
                file_path=file_entry,
                source=source,
                entity=entity,
                execution_date=exec_date,
                file_format=file_format,
                id_correlation=corr_id,
            )
            results.append(result)

        return results


"""Unit tests for operational file landing extractor (Task 2.4)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
import pandas as pd
import pytest
from moto import mock_aws

from src.common.s3_client import S3Client
from src.ingestion.file_landing import FileLandingExtractor, FileLandingResult


@pytest.fixture
def s3_env():
    """Spin up simulated in-memory AWS S3 service via moto."""
    with mock_aws():
        bucket_name = "test-saudi-ecom-lake"
        s3 = boto3.client("s3", region_name="eu-west-1")
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
        )
        yield {"bucket": bucket_name, "client": s3}


def test_land_parquet_and_csv_files(s3_env: dict[str, Any], tmp_path: Path):
    """Seam 1: Verify landing Parquet and CSV files into S3 Raw Zone with Hive partitions."""
    s3_client = S3Client(bucket_name=s3_env["bucket"], region_name="eu-west-1")
    extractor = FileLandingExtractor(s3_client=s3_client)

    # 1. Parquet file
    sample_shipments = pd.DataFrame([
        {"shipment_id": "SHP-001", "carrier": "SMSA", "destination_city": "Riyadh", "fee_halalas": 2500},
        {"shipment_id": "SHP-002", "carrier": "Aramex", "destination_city": "Jeddah", "fee_halalas": 3000},
        {"shipment_id": "SHP-003", "carrier": "SPL", "destination_city": "Dammam", "fee_halalas": 2000},
    ])
    parquet_path = tmp_path / "shipments_batch.parquet"
    sample_shipments.to_parquet(parquet_path, index=False)

    exec_date = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
    result_parquet = extractor.land_file(
        file_path=parquet_path,
        source="logistics",
        entity="shipments",
        execution_date=exec_date,
    )

    assert isinstance(result_parquet, FileLandingResult)
    assert result_parquet.source == "logistics"
    assert result_parquet.entity == "shipments"
    assert result_parquet.record_count == 3
    assert result_parquet.file_format == "parquet"
    assert "raw/logistics/shipments/year=2026/month=10/day=28/" in result_parquet.s3_key

    # Verify object in S3
    head = s3_env["client"].head_object(Bucket=s3_env["bucket"], Key=result_parquet.s3_key)
    assert head["ResponseMetadata"]["HTTPStatusCode"] == 200

    # 2. CSV file
    sample_deliveries = pd.DataFrame([
        {"delivery_id": "DEL-001", "attempt": 1, "status": "DELIVERED"},
        {"delivery_id": "DEL-002", "attempt": 1, "status": "FAILED"},
    ])
    csv_path = tmp_path / "deliveries_batch.csv"
    sample_deliveries.to_csv(csv_path, index=False)

    result_csv = extractor.land_file(
        file_path=csv_path,
        source="logistics",
        entity="deliveries",
        execution_date=exec_date,
    )

    assert result_csv.record_count == 2
    assert result_csv.file_format == "parquet"  # S3Client defaults to columnar Parquet
    assert "raw/logistics/deliveries/year=2026/month=10/day=28/" in result_csv.s3_key


def test_land_excel_spreadsheet_file(s3_env: dict[str, Any], tmp_path: Path):
    """Seam 2: Verify landing Excel spreadsheet (.xlsx) with sheet selection into S3 Raw Zone."""
    s3_client = S3Client(bucket_name=s3_env["bucket"], region_name="eu-west-1")
    extractor = FileLandingExtractor(s3_client=s3_client)

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "operational_targets"
    ws.append(["Region", "Monthly_Target_SAR", "Quarterly_Target_SAR", "Delivery_SLA_Hours"])
    ws.append(["Riyadh", 2500000, 7500000, 24])
    ws.append(["Jeddah", 1800000, 5400000, 24])

    excel_path = tmp_path / "targets_2026.xlsx"
    wb.save(excel_path)

    exec_date = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
    result = extractor.land_file(
        file_path=excel_path,
        source="logistics",
        entity="operational_targets",
        execution_date=exec_date,
        sheet_name="operational_targets",
    )

    assert result.record_count == 2
    assert result.source == "logistics"
    assert result.entity == "operational_targets"
    assert "raw/logistics/operational_targets/year=2026/month=10/day=28/" in result.s3_key

    # Verify S3 upload
    head = s3_env["client"].head_object(Bucket=s3_env["bucket"], Key=result.s3_key)
    assert head["ResponseMetadata"]["HTTPStatusCode"] == 200


def test_land_file_missing_path_raises_permanent_error(s3_env: dict[str, Any]):
    """Seam 3: Verify missing file raises PermanentError with FILE_NOT_FOUND."""
    s3_client = S3Client(bucket_name=s3_env["bucket"], region_name="eu-west-1")
    extractor = FileLandingExtractor(s3_client=s3_client)

    from src.common.exceptions import PermanentError

    with pytest.raises(PermanentError) as exc_info:
        extractor.land_file("non_existent_file.parquet", source="logistics", entity="shipments")
    assert exc_info.value.error_code == "FILE_NOT_FOUND"


def test_land_empty_file_raises_permanent_error(s3_env: dict[str, Any], tmp_path: Path):
    """Seam 3: Verify empty file raises PermanentError with EMPTY_OPERATIONAL_FILE."""
    s3_client = S3Client(bucket_name=s3_env["bucket"], region_name="eu-west-1")
    extractor = FileLandingExtractor(s3_client=s3_client)

    from src.common.exceptions import PermanentError

    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("")

    with pytest.raises(PermanentError) as exc_info:
        extractor.land_file(empty_csv, source="logistics", entity="shipments")
    assert exc_info.value.error_code == "EMPTY_OPERATIONAL_FILE"


def test_land_file_schema_validation_failure(s3_env: dict[str, Any], tmp_path: Path):
    """Seam 3: Verify missing required columns raises PermanentError with SCHEMA_VALIDATION_ERROR."""
    s3_client = S3Client(bucket_name=s3_env["bucket"], region_name="eu-west-1")
    extractor = FileLandingExtractor(s3_client=s3_client)

    from src.common.exceptions import PermanentError

    invalid_df = pd.DataFrame([{"wrong_col": 123}])
    invalid_csv = tmp_path / "invalid.csv"
    invalid_df.to_csv(invalid_csv, index=False)

    with pytest.raises(PermanentError) as exc_info:
        extractor.land_file(
            invalid_csv,
            source="logistics",
            entity="shipments",
            required_columns=["shipment_id", "carrier"],
        )
    assert exc_info.value.error_code == "SCHEMA_VALIDATION_ERROR"


def test_land_directory_batch(s3_env: dict[str, Any], tmp_path: Path):
    """Seam 4: Verify batch landing all operational files from a directory into S3 Raw Zone."""
    s3_client = S3Client(bucket_name=s3_env["bucket"], region_name="eu-west-1")
    extractor = FileLandingExtractor(s3_client=s3_client)

    feed_dir = tmp_path / "logistics_feed"
    feed_dir.mkdir()

    df_ship = pd.DataFrame([{"shipment_id": "SHP-1", "city": "Riyadh"}, {"shipment_id": "SHP-2", "city": "Jeddah"}])
    df_ship.to_parquet(feed_dir / "shipments.parquet", index=False)

    df_del = pd.DataFrame([{"delivery_id": "DEL-1", "status": "DELIVERED"}])
    df_del.to_csv(feed_dir / "deliveries.csv", index=False)

    exec_date = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
    results = extractor.land_directory(
        directory_path=feed_dir,
        source="logistics",
        execution_date=exec_date,
    )

    assert len(results) == 2
    entities = {r.entity for r in results}
    assert entities == {"shipments", "deliveries"}
    for r in results:
        assert "raw/logistics/" in r.s3_key
        head = s3_env["client"].head_object(Bucket=s3_env["bucket"], Key=r.s3_key)
        assert head["ResponseMetadata"]["HTTPStatusCode"] == 200


def test_land_directory_deduplicates_by_stem_preferring_parquet(s3_env: dict[str, Any], tmp_path: Path):
    """Seam 4: Verify directory landing deduplicates multiple file types for same stem, preferring parquet."""
    s3_client = S3Client(bucket_name=s3_env["bucket"], region_name="eu-west-1")
    extractor = FileLandingExtractor(s3_client=s3_client)

    feed_dir = tmp_path / "dedup_feed"
    feed_dir.mkdir()

    # Both parquet and csv exist for 'shipments'
    df_ship = pd.DataFrame([{"shipment_id": "SHP-1", "city": "Riyadh"}])
    df_ship.to_parquet(feed_dir / "shipments.parquet", index=False)
    df_ship.to_csv(feed_dir / "shipments.csv", index=False)

    results = extractor.land_directory(directory_path=feed_dir, source="logistics")
    assert len(results) == 1
    assert results[0].entity == "shipments"
    assert results[0].file_path.endswith(".parquet")





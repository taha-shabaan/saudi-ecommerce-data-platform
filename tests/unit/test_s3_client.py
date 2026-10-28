"""Unit & Live Integration tests for S3 storage client and bronze/raw zone partitioning."""

from datetime import UTC, datetime
import gzip
import io
import json
from typing import Any

import boto3
from moto import mock_aws
import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.common.config import settings
from src.common.exceptions import PermanentError
from src.common.s3_client import S3Client


@pytest.fixture
def sample_saudi_orders() -> list[dict[str, Any]]:
    """Sample realistic Saudi eCommerce orders for testing."""
    return [
        {"order_id": "ORD-001", "name_ar": "محمد الغامدي", "amount_halalas": 15000, "city": "Riyadh"},
        {"order_id": "ORD-002", "name_ar": "سارة القحطاني", "amount_halalas": 32000, "city": "Jeddah"},
    ]


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


def test_build_partition_keys():
    """Verify deterministic partition path structure conforming to data lake contract."""
    client = S3Client(bucket_name="dummy-bucket", region_name="eu-west-1")
    dt = datetime(2026, 10, 27, 14, 30, 0, tzinfo=UTC)

    # Test generic build_partition_key
    key_silver = client.build_partition_key(
        source="postgres",
        entity="orders",
        filename="orders.parquet",
        zone="silver",
        partition_date=dt,
    )
    assert key_silver == "silver/postgres/orders/year=2026/month=10/day=27/orders.parquet"

    # Test bronze shorthand
    key_bronze = client.build_bronze_partition_key(
        source="postgres",
        entity="orders",
        filename="orders.json.gz",
        partition_date=dt,
    )
    assert key_bronze == "bronze/postgres/orders/year=2026/month=10/day=27/orders.json.gz"


def test_upload_json_records_compressed(s3_env, sample_saudi_orders):
    """Verify records are serialized to gzipped UTF-8 JSON lines and uploaded to S3."""
    bucket_name = s3_env["bucket"]
    client = S3Client(bucket_name=bucket_name)

    dt = datetime(2026, 10, 27, tzinfo=UTC)
    s3_key = client.upload_json_records(
        records=sample_saudi_orders,
        source="postgres",
        entity="orders",
        partition_date=dt,
        filename_prefix="batch_01",
    )

    assert s3_key.startswith("bronze/postgres/orders/year=2026/month=10/day=27/batch_01_")
    assert s3_key.endswith(".json.gz")

    # Read back directly from S3 and decompress
    s3_obj = s3_env["client"].get_object(Bucket=bucket_name, Key=s3_key)
    raw_compressed = s3_obj["Body"].read()
    decompressed = gzip.decompress(raw_compressed).decode("utf-8")
    lines = [json.loads(line) for line in decompressed.strip().split("\n")]

    assert len(lines) == 2
    assert lines[0]["name_ar"] == "محمد الغامدي"
    assert lines[1]["amount_halalas"] == 32000


def test_upload_parquet_records(s3_env, sample_saudi_orders):
    """Verify records are serialized to Snappy Parquet and uploaded to S3."""
    bucket_name = s3_env["bucket"]
    client = S3Client(bucket_name=bucket_name)

    dt = datetime(2026, 10, 27, tzinfo=UTC)
    s3_key = client.upload_parquet_records(
        records=sample_saudi_orders,
        source="postgres",
        entity="orders",
        partition_date=dt,
        filename_prefix="parquet_batch_01",
    )

    assert s3_key.startswith("bronze/postgres/orders/year=2026/month=10/day=27/parquet_batch_01_")
    assert s3_key.endswith(".parquet")

    # Read back directly from S3 and deserialize Parquet
    s3_obj = s3_env["client"].get_object(Bucket=bucket_name, Key=s3_key)
    parquet_bytes = s3_obj["Body"].read()
    table = pq.read_table(io.BytesIO(parquet_bytes))
    loaded_records = table.to_pylist()

    assert len(loaded_records) == 2
    assert loaded_records[0]["order_id"] == "ORD-001"
    assert loaded_records[0]["name_ar"] == "محمد الغامدي"
    assert loaded_records[1]["city"] == "Jeddah"


def test_upload_parquet_from_pandas_dataframe(s3_env, sample_saudi_orders):
    """Verify uploading a pandas DataFrame directly converts to Parquet seamlessly."""
    bucket_name = s3_env["bucket"]
    client = S3Client(bucket_name=bucket_name)
    df = pd.DataFrame(sample_saudi_orders)

    s3_key = client.upload_parquet_records(
        records=df,
        source="postgres",
        entity="orders",
        filename_prefix="df_batch",
    )

    assert s3_key.endswith(".parquet")
    s3_obj = s3_env["client"].get_object(Bucket=bucket_name, Key=s3_key)
    table = pq.read_table(io.BytesIO(s3_obj["Body"].read()))
    loaded_df = table.to_pandas()
    assert len(loaded_df) == 2
    assert loaded_df.iloc[0]["city"] == "Riyadh"


@pytest.mark.parametrize("method_name", ["upload_json_records", "upload_parquet_records"])
def test_upload_empty_records_raises_error(s3_env, method_name):
    """DRY validation: uploading empty records in either format raises PermanentError."""
    client = S3Client(bucket_name=s3_env["bucket"])
    upload_fn = getattr(client, method_name)

    with pytest.raises(PermanentError, match="Cannot upload empty record set"):
        upload_fn(
            records=[],
            source="postgres",
            entity="customers",
        )


def test_list_objects_and_check_existence(s3_env):
    """Verify listing and head-checking partitions in S3."""
    bucket_name = s3_env["bucket"]
    client = S3Client(bucket_name=bucket_name)

    records = [{"id": 1, "test": "val"}]
    key = client.upload_json_records(
        records=records,
        source="operational_api",
        entity="payments",
        partition_date=datetime(2026, 10, 27, tzinfo=UTC),
    )

    assert client.object_exists(key=key) is True
    assert client.object_exists(key="bronze/postgres/orders/does_not_exist.parquet") is False

    keys = client.list_objects(prefix="bronze/operational_api/payments/year=2026/month=10/")
    assert len(keys) == 1
    assert keys[0] == key


@pytest.mark.live_aws
def test_live_aws_s3_upload_and_read():
    """Live test that uploads both JSON and Parquet and verifies round-trip from AWS S3."""
    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        pytest.skip("AWS credentials not configured in environment")

    client = S3Client(
        bucket_name=settings.env_storage_bucket,
        region_name=settings.aws_default_region,
    )

    live_records = [
        {
            "order_id": "ORD-LIVE-SAUDI-001",
            "customer_name": "سلطان العتيبي",
            "region": "Riyadh Region",
            "city": "Riyadh",
            "payment_method": "MADA",
            "subtotal_halalas": 45000,
            "vat_halalas": 6750,
            "total_halalas": 51750,
            "created_at": datetime.now(UTC).isoformat(),
        },
        {
            "order_id": "ORD-LIVE-SAUDI-002",
            "customer_name": "نورة الشمري",
            "region": "Eastern Province",
            "city": "Dammam",
            "payment_method": "APPLE_PAY",
            "subtotal_halalas": 28000,
            "vat_halalas": 4200,
            "total_halalas": 32200,
            "created_at": datetime.now(UTC).isoformat(),
        },
    ]

    # 1. Live JSON upload & read-back
    json_key = client.upload_json_records(
        records=live_records,
        source="postgres",
        entity="orders",
        filename_prefix="live_test_json",
    )
    assert client.object_exists(json_key) is True

    # 2. Live Parquet upload & read-back
    parquet_key = client.upload_parquet_records(
        records=live_records,
        source="postgres",
        entity="orders",
        filename_prefix="live_test_parquet",
    )
    assert client.object_exists(parquet_key) is True

    # Read back and verify Parquet directly from AWS
    s3_response = client._s3_client.get_object(
        Bucket=settings.env_storage_bucket,
        Key=parquet_key,
    )
    table = pq.read_table(io.BytesIO(s3_response["Body"].read()))
    verified_records = table.to_pylist()

    assert len(verified_records) == 2
    assert verified_records[0]["order_id"] == "ORD-LIVE-SAUDI-001"
    assert verified_records[0]["city"] == "Riyadh"
    assert verified_records[1]["city"] == "Dammam"

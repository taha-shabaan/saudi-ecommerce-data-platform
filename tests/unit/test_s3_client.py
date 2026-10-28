"""Unit & Live Integration tests for S3 storage client and raw zone partitioning."""

from datetime import UTC, datetime
import gzip
import json
import boto3
from moto import mock_aws
import pytest
from src.common.config import settings
from src.common.config import settings
from src.common.exceptions import PermanentError
from src.common.s3_client import S3Client


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


def test_build_bronze_partition_key():
    """Verify deterministic partition path structure conforming to data lake contract."""
    
    client = S3Client(bucket_name="dummy-bucket", region_name="eu-west-1")
    dt = datetime(2026, 10, 27, 14, 30, 0, tzinfo=UTC)

    key = client.build_bronze_partition_key(
        source="postgres",
        entity="orders",
        filename="orders_extract_01.json.gz",
        partition_date=dt,
    )
    assert key == "bronze/postgres/orders/year=2026/month=10/day=27/orders_extract_01.json.gz"


def test_upload_json_records_compressed(s3_env):
    """Verify records are serialized to gzipped UTF-8 JSON lines and uploaded to S3."""
    bucket_name = s3_env["bucket"]
    client = S3Client(bucket_name=bucket_name)

    sample_records = [
        {"order_id": "ORD-001", "name_ar": "محمد الغامدي", "amount_halalas": 15000},
        {"order_id": "ORD-002", "name_ar": "سارة القحطاني", "amount_halalas": 32000},
    ]

    dt = datetime(2026, 10, 27, tzinfo=UTC)
    s3_key = client.upload_json_records(
        records=sample_records,
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


def test_upload_empty_records_raises_error(s3_env):
    """Uploading empty list should be prevented or handled safely."""
    client = S3Client(bucket_name=s3_env["bucket"])
    with pytest.raises(PermanentError, match="Cannot upload empty record set"):
        client.upload_json_records(
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
    assert client.object_exists(key="bronze/postgres/orders/does_not_exist.json.gz") is False

    keys = client.list_objects(prefix="bronze/operational_api/payments/year=2026/month=10/")
    assert len(keys) == 1
    assert keys[0] == key


@pytest.mark.live_aws
def test_live_aws_s3_upload_and_read():
    """Live test that uploads and verifies real data in the configured AWS S3 bucket."""
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

    key = client.upload_json_records(
        records=live_records,
        source="postgres",
        entity="orders",
        filename_prefix="live_test",
    )

    assert client.object_exists(key) is True
    listed = client.list_objects(prefix="bronze/postgres/orders/")
    assert key in listed



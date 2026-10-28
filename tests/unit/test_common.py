"""Unit tests for src/common module: config, logging, and exceptions."""

import json
import logging
import pytest
from src.common.config import AppSettings
from src.common.exceptions import (
    DataQualityError,
    PermanentError,
    PlatformError,
    TransientError,
)
from src.common.logging import JSONFormatter, generate_correlation_id, get_logger, sanitize_payload


class TestCommonExceptions:
    """Test exception serialization and classification."""

    def test_platform_error_serialization(self):
        err = PlatformError(
            message="Internal error",
            error_code="TEST_CODE",
            id_correlation="wf_123",
            context={"step": "ingestion"},
        )
        serialized = err.to_dict()
        assert serialized["error_class"] == "PlatformError"
        assert serialized["error_code"] == "TEST_CODE"
        assert serialized["error_message"] == "Internal error"
        assert serialized["id_correlation"] == "wf_123"
        assert serialized["context"] == {"step": "ingestion"}

    def test_transient_error_is_subclass(self):
        err = TransientError("Database timeout")
        assert isinstance(err, PlatformError)
        assert err.error_code == "TRANSIENT_UPSTREAM_ERROR"

    def test_permanent_error_is_subclass(self):
        err = PermanentError("Invalid schema format")
        assert isinstance(err, PlatformError)
        assert err.error_code == "PERMANENT_CONTRACT_ERROR"

    def test_data_quality_error_is_circuit_breaker(self):
        err = DataQualityError("Negative halalas detected in order total")
        assert isinstance(err, PlatformError)
        assert err.error_code == "DATA_QUALITY_CIRCUIT_BREAKER"


class TestCommonLogging:
    """Test JSON structured logging and PII masking."""

    def test_correlation_id_generation(self):
        cid = generate_correlation_id()
        assert cid.startswith("wf_ecom_")
        assert len(cid) > 12

    def test_sensitive_payload_masking(self):
        raw_payload = {
            "order_id": "ORD-123",
            "password": "secret_password",
            "api_key": "sk_live_12345",
            "nested": {
                "user_token": "bearer_abc",
                "customer_name": "Taha",
            },
        }
        sanitized = sanitize_payload(raw_payload)
        assert sanitized["order_id"] == "ORD-123"
        assert sanitized["password"] == "********"
        assert sanitized["api_key"] == "********"
        assert sanitized["nested"]["user_token"] == "********"
        assert sanitized["nested"]["customer_name"] == "Taha"

    def test_json_formatter_output(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Order processed successfully",
            args=(),
            exc_info=None,
        )
        setattr(record, "id_correlation", "wf_test_123")
        setattr(record, "payload", {"total_halalas": 15000, "password": "super_secret"})

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Order processed successfully"
        assert parsed["id_correlation"] == "wf_test_123"
        assert parsed["payload"]["total_halalas"] == 15000
        assert parsed["payload"]["password"] == "********"


class TestCommonConfig:
    """Test Pydantic settings loading and defaults."""

    def test_default_settings(self, monkeypatch):
        # Clear environment overrides to test pure default values
        monkeypatch.delenv("ENV_STORAGE_BUCKET", raising=False)
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
        config = AppSettings(
            _env_file=None,  # ignore local .env for isolated test
            postgres_host="test_host",
            postgres_port=5432,
            postgres_db="test_db",
            postgres_user="test_user",
            postgres_password="test_password",
        )
        assert config.environment == "development"
        assert config.default_timezone == "Asia/Riyadh"
        assert config.env_storage_bucket == "saudi-ecommerce-data-lake-dev"
        assert (
            config.postgres_connection_url
            == "postgresql+psycopg2://test_user:test_password@test_host:5432/test_db"
        )


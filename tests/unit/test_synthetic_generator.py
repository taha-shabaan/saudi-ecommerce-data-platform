"""Unit test suite for Saudi synthetic data generator & sources loader."""

import os
from pathlib import Path

import pandas as pd
import pytest

from src.common.exceptions import PermanentError
from src.ingestion.synthetic_data_generator import (
    ALL_SOURCE_ENTITIES,
    ORDER_STATUSES,
    PAYMENT_METHODS,
    SAUDI_PRODUCTS,
    SAUDI_REGIONS,
    SaudiSyntheticGenerator,
    _clean_bool_value,
    _clean_halalas_value,
    _clean_id_value,
    _clean_int_value,
    _clean_timestamp_value,
)


def test_customer_generation():
    """Verify generated customers comply with Saudi identity and contact rules."""
    generator = SaudiSyntheticGenerator(seed=42)
    customers = generator.generate_customers(count=50)

    assert len(customers) == 50
    for customer in customers:
        assert customer["customer_id"].startswith("CUST-")
        assert customer["phone"].startswith("+9665")
        assert len(customer["phone"]) == 13  # +9665 + 8 digits
        assert any(r["name_en"] == customer["region_en"] for r in SAUDI_REGIONS)
        assert any(customer["city_en"] in r["cities"] for r in SAUDI_REGIONS)
        assert customer["created_at"] is not None


def test_product_catalog_generation():
    """Verify catalog items have positive prices in integer Halalas and valid categories."""
    generator = SaudiSyntheticGenerator(seed=42)
    products = generator.generate_products()

    assert len(products) >= 12
    for product in products:
        assert product["product_id"].startswith("PROD-")
        assert product["unit_price_halalas"] > 0
        assert isinstance(product["unit_price_halalas"], int)
        assert product["unit_cost_halalas"] > 0
        assert product["unit_cost_halalas"] < product["unit_price_halalas"]


def test_order_and_items_generation():
    """Verify order totals, items, 15% VAT calculation, and payment distribution."""
    generator = SaudiSyntheticGenerator(seed=42)
    customers = generator.generate_customers(count=20)
    products = generator.generate_products()

    orders, items, payments = generator.generate_transactions(
        customers=customers,
        products=products,
        order_count=100,
    )

    assert len(orders) == 100
    assert len(items) >= 100
    assert len(payments) == 100

    order_map = {o["order_id"]: o for o in orders}

    # Verify order item totals match line items
    item_sums: dict[str, int] = {}
    for item in items:
        oid = item["order_id"]
        item_sums[oid] = item_sums.get(oid, 0) + item["total_item_halalas"]
        assert item["quantity"] >= 1
        assert item["unit_price_halalas"] > 0

    for oid, calculated_subtotal in item_sums.items():
        order = order_map[oid]
        assert order["subtotal_halalas"] == calculated_subtotal
        assert order["vat_halalas"] == round(calculated_subtotal * 0.15)
        expected_total = (
            order["subtotal_halalas"]
            - order["discount_halalas"]
            + order["vat_halalas"]
            + order["shipping_fee_halalas"]
        )
        assert order["total_halalas"] == expected_total
        assert order["status"] in ORDER_STATUSES
        assert order["payment_method"] in PAYMENT_METHODS


def test_operational_files_generation(tmp_path: Path):
    """Verify creation of sales targets Excel spreadsheet and catalog overrides CSV."""
    generator = SaudiSyntheticGenerator(seed=42)
    targets_path = str(tmp_path / "sales_targets_2026.xlsx")
    overrides_path = str(tmp_path / "catalog_overrides.csv")

    generator.generate_operational_files(
        excel_path=targets_path,
        csv_path=overrides_path,
        use_sources=False,
    )

    assert os.path.exists(targets_path)
    assert os.path.exists(overrides_path)
    assert os.path.getsize(targets_path) > 0
    assert os.path.getsize(overrides_path) > 0


def test_sources_discovery():
    """Verify sources directory discovery and entity enumeration across formats."""
    generator = SaudiSyntheticGenerator(seed=42)
    sources_dir = generator.get_sources_dir()
    assert sources_dir is not None
    assert sources_dir.exists()

    parquet_entities = generator.get_available_source_entities(format="parquet")
    assert set(ALL_SOURCE_ENTITIES).issubset(set(parquet_entities))

    csv_entities = generator.get_available_source_entities(format="csv")
    assert set(ALL_SOURCE_ENTITIES).issubset(set(csv_entities))

    json_entities = generator.get_available_source_entities(format="json")
    assert set(ALL_SOURCE_ENTITIES).issubset(set(json_entities))

    xlsx_entities = generator.get_available_source_entities(format="xlsx")
    assert set(ALL_SOURCE_ENTITIES).issubset(set(xlsx_entities))


def test_load_source_table_parquet():
    """Verify loading raw and sanitized DataFrames from Parquet source files."""
    generator = SaudiSyntheticGenerator(seed=42)
    df_raw = generator.load_source_table("customers", format="parquet", sanitize=False)
    assert isinstance(df_raw, pd.DataFrame)
    assert len(df_raw) == 1000
    assert "customer_id" in df_raw.columns

    df_clean = generator.load_source_table("customers", format="parquet", sanitize=True)
    assert isinstance(df_clean, pd.DataFrame)
    assert len(df_clean) == 1000
    assert pd.api.types.is_datetime64_any_dtype(df_clean["created_at"])


def test_load_source_table_csv():
    """Verify loading source table from CSV."""
    generator = SaudiSyntheticGenerator(seed=42)
    df_csv = generator.load_source_table("products", format="csv", sanitize=True)
    assert isinstance(df_csv, pd.DataFrame)
    assert len(df_csv) == 2000
    assert pd.api.types.is_integer_dtype(df_csv["unit_price_halalas"])


def test_load_source_table_json():
    """Verify loading source table from bundled JSON."""
    generator = SaudiSyntheticGenerator(seed=42)
    df_json = generator.load_source_table("orders", format="json", sanitize=True)
    assert isinstance(df_json, pd.DataFrame)
    assert len(df_json) == 5000
    assert pd.api.types.is_integer_dtype(df_json["total_halalas"])


def test_load_source_table_xlsx():
    """Verify loading source table from multi-sheet Excel."""
    generator = SaudiSyntheticGenerator(seed=42)
    df_xlsx = generator.load_source_table("order_items", format="xlsx", sanitize=True)
    assert isinstance(df_xlsx, pd.DataFrame)
    assert len(df_xlsx) == 10000
    assert pd.api.types.is_integer_dtype(df_xlsx["quantity"])


def test_load_all_sources():
    """Verify bulk loading of all available source tables."""
    generator = SaudiSyntheticGenerator(seed=42)
    sources_dict = generator.load_all_sources(format="parquet", sanitize=False)
    assert set(ALL_SOURCE_ENTITIES).issubset(set(sources_dict.keys()))
    for df_table in sources_dict.values():
        assert len(df_table) > 0


def test_cleaning_helpers():
    """Verify granular sanitization helpers handle corrupted strings and edge cases."""
    assert _clean_halalas_value("761_CORRUPTED") == 761
    assert _clean_halalas_value("SAR 12500") == 12500
    assert _clean_halalas_value(None) == 0
    assert _clean_halalas_value(4500) == 4500
    assert _clean_halalas_value(199.99) == 200

    assert _clean_int_value("10_items", default_val=1) == 10
    assert _clean_int_value(None, default_val=1) == 1
    assert _clean_int_value(3, default_val=1) == 3

    assert _clean_bool_value("true") is True
    assert _clean_bool_value("1") is True
    assert _clean_bool_value(True) is True
    assert _clean_bool_value("false") is False
    assert _clean_bool_value("0") is False
    assert _clean_bool_value(None) is False

    assert _clean_id_value("   CUST-12345   ", entity_prefix="CUST") == "CUST-12345"
    assert _clean_id_value("NULL", entity_prefix="CUST").startswith("CUST-")
    assert _clean_id_value(None, entity_prefix="ORD").startswith("ORD-")

    valid_ts = _clean_timestamp_value("2026-10-28T10:00:00+00:00")
    assert valid_ts is not None and valid_ts.startswith("2026-10-28")
    assert _clean_timestamp_value("Lorem ipsum dolor sit amet", default_iso="2025-01-01T00:00:00+00:00") == "2025-01-01T00:00:00+00:00"
    assert _clean_timestamp_value("Lorem ipsum", default_iso=None) is None


def test_sanitize_source_table():
    """Verify table-level sanitization converts corrupted strings to strictly typed columns."""
    generator = SaudiSyntheticGenerator(seed=42)
    dirty_data = {
        "customer_id": ["  C-001  ", "NULL", None],
        "name_en": [" Ahmed Al-Ghamdi  ", "Sara", " Khalid "],
        "unit_price_halalas": ["4500_CORRUPTED", "1200", None],
        "quantity": ["5_items", "1", None],
        "is_cod": ["true", "False", "1"],
        "created_at": ["2026-10-28T12:00:00Z", "Lorem ipsum corrupt text", None],
        "updated_at": ["Lorem ipsum text", "2026-10-28T15:00:00Z", ""],
    }
    df_dirty = pd.DataFrame(dirty_data)
    df_sanitized = generator.sanitize_source_table("customers", df_dirty)

    assert df_sanitized["customer_id"].iloc[0] == "C-001"
    assert df_sanitized["customer_id"].iloc[1].startswith("CUST-")
    assert df_sanitized["customer_id"].iloc[2].startswith("CUST-")
    assert df_sanitized["name_en"].iloc[0] == "Ahmed Al-Ghamdi"

    assert df_sanitized["unit_price_halalas"].tolist() == [4500, 1200, 0]
    assert df_sanitized["quantity"].tolist() == [5, 1, 1]
    assert df_sanitized["is_cod"].tolist() == [True, False, True]

    assert pd.api.types.is_datetime64_any_dtype(df_sanitized["created_at"])
    assert pd.api.types.is_datetime64_any_dtype(df_sanitized["updated_at"])


def test_enrich_catalog_from_sources():
    """Verify enriching in-memory catalog with authentic benchmark source records."""
    generator = SaudiSyntheticGenerator(seed=42)
    initial_product_count = len(SAUDI_PRODUCTS)
    success = generator.enrich_catalog_from_sources(format="parquet")
    assert success is True
    assert len(SAUDI_PRODUCTS) >= initial_product_count


def test_generate_operational_files_from_sources(tmp_path: Path):
    """Verify generating operational target files directly derived from benchmark sources."""
    generator = SaudiSyntheticGenerator(seed=42)
    targets_path = str(tmp_path / "targets_from_sources.xlsx")
    overrides_path = str(tmp_path / "overrides_from_sources.csv")

    generator.generate_operational_files(
        excel_path=targets_path,
        csv_path=overrides_path,
        use_sources=True,
        format="parquet",
    )

    assert os.path.exists(targets_path)
    assert os.path.exists(overrides_path)
    assert os.path.getsize(targets_path) > 0
    assert os.path.getsize(overrides_path) > 0

    df_overrides = pd.read_csv(overrides_path)
    assert len(df_overrides) > 0
    assert "product_id" in df_overrides.columns
    assert "special_discount_pct" in df_overrides.columns


def test_seed_postgres_from_sources_fallback():
    """Verify graceful handling when PostgreSQL connection is unreachable."""
    generator = SaudiSyntheticGenerator(seed=42)
    invalid_url = "postgresql+psycopg2://dummy_user:dummy_pass@localhost:9999/dummy_db"
    result = generator.seed_postgres_from_sources(connection_url=invalid_url, format="parquet")
    assert result is False


def test_unsupported_format_raises_permanent_error():
    """Verify querying an unsupported format immediately raises PermanentError."""
    generator = SaudiSyntheticGenerator(seed=42)
    with pytest.raises(PermanentError) as exc_info:
        generator.load_source_table("customers", format="xml")
    assert "Unsupported source format" in str(exc_info.value)


def test_missing_entity_raises_permanent_error():
    """Verify querying a non-existent entity raises PermanentError."""
    generator = SaudiSyntheticGenerator(seed=42)
    with pytest.raises(PermanentError) as exc_info:
        generator.load_source_table("non_existent_table_xyz", format="parquet")
    assert "not found" in str(exc_info.value)

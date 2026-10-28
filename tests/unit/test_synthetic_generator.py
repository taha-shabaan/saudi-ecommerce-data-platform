"""Unit test suite for Saudi synthetic data generator."""

import os

from src.ingestion.synthetic_data_generator import (
    ORDER_STATUSES,
    PAYMENT_METHODS,
    SAUDI_PRODUCTS,
    SAUDI_REGIONS,
    SaudiSyntheticGenerator,
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

    assert len(products) == len(SAUDI_PRODUCTS)
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
    item_sums = {}
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


def test_operational_files_generation(tmp_path):
    """Verify creation of sales targets Excel spreadsheet and catalog overrides CSV."""
    generator = SaudiSyntheticGenerator(seed=42)
    targets_path = str(tmp_path / "sales_targets_2026.xlsx")
    overrides_path = str(tmp_path / "catalog_overrides.csv")

    generator.generate_operational_files(
        excel_path=targets_path,
        csv_path=overrides_path,
    )

    assert os.path.exists(targets_path)
    assert os.path.exists(overrides_path)
    assert os.path.getsize(targets_path) > 0
    assert os.path.getsize(overrides_path) > 0

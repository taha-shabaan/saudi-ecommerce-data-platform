"""Enterprise Sources Distribution & Local Database Seeding Utility.

Extracts synthetic benchmark datasets from sources/, distributes entities across
authoritative source channels (PostgreSQL OLTP, Excel/CSV catalogs, 3PL logistics),
and generates initialization DDL for docker-compose.
"""

from __future__ import annotations

import argparse
import os
import random
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import openpyxl
import pandas as pd
import psycopg2
import pyarrow.parquet as pq
from psycopg2.extras import execute_batch

# Source and target directories
ROOT_DIR = Path(__file__).resolve().parent.parent
SOURCES_DIR = ROOT_DIR / "sources"
PARQUET_DIR = SOURCES_DIR / "sch_d053e26259_parquet"
CSV_DIR = SOURCES_DIR / "sch_d053e26259_csv"
SQL_DDL_DIR = ROOT_DIR / "sql" / "ddl"
DATA_DIR = ROOT_DIR / "data"
LOGISTICS_DIR = DATA_DIR / "logistics"
CATALOGS_DIR = DATA_DIR / "catalogs"

BASE_START_TS = datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC)
BASE_END_TS = datetime(2026, 10, 28, 23, 59, 59, tzinfo=UTC)
TIMELINE_SECONDS = int((BASE_END_TS - BASE_START_TS).total_seconds())


def sanitize_int(val: Any, default: int = 0) -> int:
    """Extract clean integer amount from string or corrupted numeric representation."""
    if val is None or pd.isna(val):
        return default
    if isinstance(val, (int, float)):
        return int(val)
    # Strip any _CORRUPTED suffix or non-digits
    match = re.search(r"-?\d+", str(val))
    if match:
        try:
            return int(match.group(0))
        except ValueError:
            return default
    return default


def sanitize_id(raw_id: Any, fallback_prefix: str, row_index: int) -> str:
    """Ensure ID is non-empty, stripped, and not a literal 'None' string."""
    if raw_id is None or pd.isna(raw_id):
        return f"{fallback_prefix}-{row_index:06d}"
    cleaned = str(raw_id).strip()
    if cleaned in ("", "None", "null", "NULL") or "_CORRUPTED" in cleaned:
        # Replace corrupted literal with deterministic clean identifier
        return f"{fallback_prefix}-{row_index:06d}"
    return cleaned


def generate_consistent_timestamps(
    row_index: int, total_rows: int, seed_prefix: str
) -> tuple[datetime, datetime]:
    """Generate deterministic, chronologically distributed created_at and updated_at."""
    rng = random.Random(f"{seed_prefix}-{row_index}")
    # Progress through the 28 days based on row order with randomized jitter
    progress = row_index / max(total_rows, 1)
    base_offset_sec = int(progress * TIMELINE_SECONDS)
    jitter_sec = rng.randint(-3600, 3600)
    created_offset = max(0, min(TIMELINE_SECONDS, base_offset_sec + jitter_sec))
    created_at = BASE_START_TS + timedelta(seconds=created_offset)

    # updated_at is equal to created_at or later (e.g. up to 48 hours later)
    update_lag_sec = rng.choice([0, 0, 0, rng.randint(300, 172800)])
    updated_at = min(BASE_END_TS, created_at + timedelta(seconds=update_lag_sec))
    return created_at, updated_at


def process_customers(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Process customer records for PostgreSQL."""
    records = []
    total = len(df)
    for idx, row in df.iterrows():
        customer_id = sanitize_id(row.get("customer_id"), "cust", idx)
        created_at, updated_at = generate_consistent_timestamps(idx, total, "cust")
        records.append({
            "customer_id": customer_id,
            "name_ar": str(row.get("name_ar", "")).strip(),
            "name_en": str(row.get("name_en", "")).strip(),
            "email": str(row.get("email", "")).strip(),
            "phone": str(row.get("phone", "")).strip(),
            "region_ar": str(row.get("region_ar", "")).strip(),
            "region_en": str(row.get("region_en", "")).strip(),
            "city_en": str(row.get("city_en", "")).strip(),
            "national_address": str(row.get("national_address", "")).strip(),
            "created_at": created_at,
            "updated_at": updated_at,
        })
    return records


def process_products(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Process product records for PostgreSQL and Excel catalog."""
    records = []
    total = len(df)
    for idx, row in df.iterrows():
        product_id = sanitize_id(row.get("product_id"), "prod", idx)
        created_at, updated_at = generate_consistent_timestamps(idx, total, "prod")
        records.append({
            "product_id": product_id,
            "name_ar": str(row.get("name_ar", "")).strip(),
            "name_en": str(row.get("name_en", "")).strip(),
            "category": str(row.get("category", "")).strip(),
            "unit_price_halalas": sanitize_int(row.get("unit_price_halalas"), 1000),
            "unit_cost_halalas": sanitize_int(row.get("unit_cost_halalas"), 600),
            "created_at": created_at,
            "updated_at": updated_at,
        })
    return records


def process_orders(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Process order records for PostgreSQL."""
    records = []
    total = len(df)
    for idx, row in df.iterrows():
        order_id = sanitize_id(row.get("order_id"), "ord", idx)
        customer_id = sanitize_id(row.get("customer_id"), "cust", idx)
        created_at, updated_at = generate_consistent_timestamps(idx, total, "ord")

        subtotal = sanitize_int(row.get("subtotal_halalas"), 1000)
        vat = sanitize_int(row.get("vat_halalas"), round(subtotal * 0.15))
        discount = sanitize_int(row.get("discount_halalas"), 0)
        shipping = sanitize_int(row.get("shipping_fee_halalas"), 2500)
        total_halalas = sanitize_int(row.get("total_halalas"), subtotal + vat + shipping - discount)

        coupon = row.get("coupon_code")
        coupon_str = str(coupon).strip() if coupon is not None and not pd.isna(coupon) else None

        records.append({
            "order_id": order_id,
            "customer_id": customer_id,
            "subtotal_halalas": subtotal,
            "vat_halalas": vat,
            "discount_halalas": discount,
            "shipping_fee_halalas": shipping,
            "total_halalas": total_halalas,
            "coupon_code": coupon_str,
            "payment_method": str(row.get("payment_method", "mada")).strip(),
            "status": str(row.get("status", "DELIVERED")).strip(),
            "shipping_city": str(row.get("shipping_city", "Riyadh")).strip(),
            "shipping_region": str(row.get("shipping_region", "Riyadh")).strip(),
            "created_at": created_at,
            "updated_at": updated_at,
        })
    return records


def process_order_items(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Process order_item records for PostgreSQL."""
    records = []
    total = len(df)
    for idx, row in df.iterrows():
        order_item_id = sanitize_id(row.get("order_item_id"), "item", idx)
        order_id = sanitize_id(row.get("order_id"), "ord", idx)
        product_id = sanitize_id(row.get("product_id"), "prod", idx)
        created_at, _ = generate_consistent_timestamps(idx, total, "item")

        qty = max(1, sanitize_int(row.get("quantity"), 1))
        unit_price = sanitize_int(row.get("unit_price_halalas"), 1000)
        unit_cost = sanitize_int(row.get("unit_cost_halalas"), 600)
        total_item = sanitize_int(row.get("total_item_halalas"), qty * unit_price)

        records.append({
            "order_item_id": order_item_id,
            "order_id": order_id,
            "product_id": product_id,
            "quantity": qty,
            "unit_price_halalas": unit_price,
            "unit_cost_halalas": unit_cost,
            "total_item_halalas": total_item,
            "created_at": created_at,
        })
    return records


def generate_source_init_sql(
    customers: list[dict[str, Any]],
    products: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    order_items: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Generate self-contained SQL DDL and DML file for PostgreSQL docker initialization."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("-- ===================================================================\n")
        f.write("-- Saudi eCommerce Data Platform: PostgreSQL Source DB Init\n")
        f.write("-- Tables: customers, products, orders, order_items\n")
        f.write("-- ===================================================================\n\n")
        f.write("BEGIN;\n\n")

        # Customers DDL
        f.write("-- 1. Customers Table\n")
        f.write("CREATE TABLE IF NOT EXISTS customers (\n")
        f.write("    customer_id VARCHAR(64) PRIMARY KEY,\n")
        f.write("    name_ar TEXT NOT NULL,\n")
        f.write("    name_en TEXT NOT NULL,\n")
        f.write("    email TEXT NOT NULL,\n")
        f.write("    phone TEXT NOT NULL,\n")
        f.write("    region_ar TEXT NOT NULL,\n")
        f.write("    region_en TEXT NOT NULL,\n")
        f.write("    city_en TEXT NOT NULL,\n")
        f.write("    national_address TEXT NOT NULL,\n")
        f.write("    created_at TIMESTAMPTZ NOT NULL,\n")
        f.write("    updated_at TIMESTAMPTZ NOT NULL\n")
        f.write(");\n")
        f.write("CREATE INDEX IF NOT EXISTS idx_customers_updated_at ON customers(updated_at);\n\n")

        # Products DDL
        f.write("-- 2. Products Table\n")
        f.write("CREATE TABLE IF NOT EXISTS products (\n")
        f.write("    product_id VARCHAR(64) PRIMARY KEY,\n")
        f.write("    name_ar TEXT NOT NULL,\n")
        f.write("    name_en TEXT NOT NULL,\n")
        f.write("    category TEXT NOT NULL,\n")
        f.write("    unit_price_halalas BIGINT NOT NULL,\n")
        f.write("    unit_cost_halalas BIGINT NOT NULL,\n")
        f.write("    created_at TIMESTAMPTZ NOT NULL,\n")
        f.write("    updated_at TIMESTAMPTZ NOT NULL\n")
        f.write(");\n")
        f.write("CREATE INDEX IF NOT EXISTS idx_products_updated_at ON products(updated_at);\n\n")

        # Orders DDL
        f.write("-- 3. Orders Table\n")
        f.write("CREATE TABLE IF NOT EXISTS orders (\n")
        f.write("    order_id VARCHAR(64) PRIMARY KEY,\n")
        f.write("    customer_id VARCHAR(64) NOT NULL,\n")
        f.write("    subtotal_halalas BIGINT NOT NULL,\n")
        f.write("    vat_halalas BIGINT NOT NULL,\n")
        f.write("    discount_halalas BIGINT NOT NULL,\n")
        f.write("    shipping_fee_halalas BIGINT NOT NULL,\n")
        f.write("    total_halalas BIGINT NOT NULL,\n")
        f.write("    coupon_code TEXT,\n")
        f.write("    payment_method TEXT NOT NULL,\n")
        f.write("    status TEXT NOT NULL,\n")
        f.write("    shipping_city TEXT NOT NULL,\n")
        f.write("    shipping_region TEXT NOT NULL,\n")
        f.write("    created_at TIMESTAMPTZ NOT NULL,\n")
        f.write("    updated_at TIMESTAMPTZ NOT NULL\n")
        f.write(");\n")
        f.write("CREATE INDEX IF NOT EXISTS idx_orders_updated_at ON orders(updated_at);\n")
        f.write("CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);\n\n")

        # Order Items DDL
        f.write("-- 4. Order Items Table\n")
        f.write("CREATE TABLE IF NOT EXISTS order_items (\n")
        f.write("    order_item_id VARCHAR(64) PRIMARY KEY,\n")
        f.write("    order_id VARCHAR(64) NOT NULL,\n")
        f.write("    product_id VARCHAR(64) NOT NULL,\n")
        f.write("    quantity INTEGER NOT NULL,\n")
        f.write("    unit_price_halalas BIGINT NOT NULL,\n")
        f.write("    unit_cost_halalas BIGINT NOT NULL,\n")
        f.write("    total_item_halalas BIGINT NOT NULL,\n")
        f.write("    created_at TIMESTAMPTZ NOT NULL\n")
        f.write(");\n")
        f.write("CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);\n")
        f.write("CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items(product_id);\n\n")

        def escape_sql(val: Any) -> str:
            if val is None:
                return "NULL"
            if isinstance(val, (int, float)):
                return str(val)
            if isinstance(val, datetime):
                return f"'{val.isoformat()}'"
            cleaned = str(val).replace("'", "''")
            return f"'{cleaned}'"

        # Batch inserts helper
        def write_inserts(table_name: str, pkey: str, data: list[dict[str, Any]], batch_size: int = 500) -> None:
            if not data:
                return
            cols = list(data[0].keys())
            cols_str = ", ".join(f'"{c}"' for c in cols)
            update_str = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in cols if c != pkey)

            f.write(f"-- Inserts for {table_name} ({len(data)} rows)\n")
            for i in range(0, len(data), batch_size):
                batch = data[i : i + batch_size]
                f.write(f'INSERT INTO "{table_name}" ({cols_str}) VALUES\n')
                row_strs = []
                for row in batch:
                    vals = ", ".join(escape_sql(row[c]) for c in cols)
                    row_strs.append(f"    ({vals})")
                f.write(",\n".join(row_strs))
                f.write(f'\nON CONFLICT ("{pkey}") DO UPDATE SET {update_str};\n\n')

        write_inserts("customers", "customer_id", customers)
        write_inserts("products", "product_id", products)
        write_inserts("orders", "order_id", orders)
        write_inserts("order_items", "order_item_id", order_items)

        f.write("COMMIT;\n")
    print(f"✅ Generated PostgreSQL init script: {output_path} ({output_path.stat().st_size / 1024 / 1024:.2f} MB)")


def create_combined_products_excel(
    products: list[dict[str, Any]], overrides_csv_path: Path, output_excel_path: Path
) -> None:
    """Combine PostgreSQL products with marketing overrides and extra attributes into an Excel file."""
    output_excel_path.parent.mkdir(parents=True, exist_ok=True)

    # Load overrides if available
    overrides_map: dict[str, dict[str, Any]] = {}
    if overrides_csv_path.exists():
        overrides_df = pd.read_csv(overrides_csv_path)
        for _, row in overrides_df.iterrows():
            pid = str(row.get("product_id", "")).strip()
            if pid:
                overrides_map[pid] = {
                    "promotional_tag": row.get("promotional_tag"),
                    "special_discount_pct": row.get("special_discount_pct"),
                }

    suppliers = ["Al-Hokair Retail", "Jarir Group", "Panda Distribution", "Extra Stores", "Danube Fine Logistics"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "products_catalog"

    headers = [
        "product_id",
        "name_ar",
        "name_en",
        "category",
        "unit_price_sar",
        "unit_cost_sar",
        "supplier_name",
        "promotional_tag",
        "special_discount_pct",
        "inventory_status",
        "created_at",
        "updated_at",
    ]
    ws.append(headers)

    for idx, prod in enumerate(products):
        pid = prod["product_id"]
        override = overrides_map.get(pid, {})
        supplier = suppliers[idx % len(suppliers)]
        tag = override.get("promotional_tag") or ("Standard Catalog" if idx % 4 != 0 else "Featured Item")
        discount = override.get("special_discount_pct") or (0 if idx % 4 != 0 else 10)

        price_sar = round(prod["unit_price_halalas"] / 100.0, 2)
        cost_sar = round(prod["unit_cost_halalas"] / 100.0, 2)

        ws.append([
            pid,
            prod["name_ar"],
            prod["name_en"],
            prod["category"],
            price_sar,
            cost_sar,
            supplier,
            tag,
            discount,
            "IN_STOCK" if idx % 10 != 0 else "LOW_STOCK",
            prod["created_at"].isoformat(),
            prod["updated_at"].isoformat(),
        ])

    wb.save(output_excel_path)
    print(f"✅ Generated combined products Excel catalog: {output_excel_path} ({len(products)} products)")


def distribute_logistics_files(
    shipments_src: Path, deliveries_src: Path, target_dir: Path
) -> None:
    """Distribute shipments and deliveries operational files to data/logistics/."""
    target_dir.mkdir(parents=True, exist_ok=True)

    if shipments_src.exists():
        ship_df = pq.read_table(shipments_src).to_pandas()
        ship_parquet = target_dir / "shipments.parquet"
        ship_csv = target_dir / "shipments.csv"
        ship_df.to_parquet(ship_parquet, index=False)
        ship_df.to_csv(ship_csv, index=False)
        print(f"✅ Distributed shipments to {ship_parquet} & {ship_csv} ({len(ship_df)} rows)")

    if deliveries_src.exists():
        del_df = pq.read_table(deliveries_src).to_pandas()
        del_parquet = target_dir / "deliveries.parquet"
        del_csv = target_dir / "deliveries.csv"
        del_df.to_parquet(del_parquet, index=False)
        del_df.to_csv(del_csv, index=False)
        print(f"✅ Distributed deliveries to {del_parquet} & {del_csv} ({len(del_df)} rows)")

    # Copy operational sales targets if present at root
    ops_targets = ROOT_DIR / "operational_sales_targets.xlsx"
    if ops_targets.exists():
        target_ops = target_dir / "operational_sales_targets.xlsx"
        target_ops.write_bytes(ops_targets.read_bytes())
        print(f"✅ Copied operational_sales_targets.xlsx to {target_ops}")


def seed_running_postgres(
    customers: list[dict[str, Any]],
    products: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    order_items: list[dict[str, Any]],
    db_url: str = "postgresql://postgres:postgres@localhost:5436/saudi_ecom_orders",
) -> None:
    """Seed the currently running PostgreSQL container directly."""
    print(f"Connecting to PostgreSQL at {db_url}...")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    # DDL
    cur.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id VARCHAR(64) PRIMARY KEY,
            name_ar TEXT NOT NULL,
            name_en TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            region_ar TEXT NOT NULL,
            region_en TEXT NOT NULL,
            city_en TEXT NOT NULL,
            national_address TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_customers_updated_at ON customers(updated_at);

        CREATE TABLE IF NOT EXISTS products (
            product_id VARCHAR(64) PRIMARY KEY,
            name_ar TEXT NOT NULL,
            name_en TEXT NOT NULL,
            category TEXT NOT NULL,
            unit_price_halalas BIGINT NOT NULL,
            unit_cost_halalas BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_products_updated_at ON products(updated_at);

        CREATE TABLE IF NOT EXISTS orders (
            order_id VARCHAR(64) PRIMARY KEY,
            customer_id VARCHAR(64) NOT NULL,
            subtotal_halalas BIGINT NOT NULL,
            vat_halalas BIGINT NOT NULL,
            discount_halalas BIGINT NOT NULL,
            shipping_fee_halalas BIGINT NOT NULL,
            total_halalas BIGINT NOT NULL,
            coupon_code TEXT,
            payment_method TEXT NOT NULL,
            status TEXT NOT NULL,
            shipping_city TEXT NOT NULL,
            shipping_region TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_orders_updated_at ON orders(updated_at);
        CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);

        CREATE TABLE IF NOT EXISTS order_items (
            order_item_id VARCHAR(64) PRIMARY KEY,
            order_id VARCHAR(64) NOT NULL,
            product_id VARCHAR(64) NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price_halalas BIGINT NOT NULL,
            unit_cost_halalas BIGINT NOT NULL,
            total_item_halalas BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
        CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items(product_id);
    """)

    def execute_upsert(table: str, pkey: str, data: list[dict[str, Any]]) -> None:
        if not data:
            return
        cols = list(data[0].keys())
        cols_str = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join(f"%({c})s" for c in cols)
        update_str = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in cols if c != pkey)
        sql = f"""
            INSERT INTO "{table}" ({cols_str}) VALUES ({placeholders})
            ON CONFLICT ("{pkey}") DO UPDATE SET {update_str}
        """
        execute_batch(cur, sql, data, page_size=1000)
        print(f"  Inserted/Upserted {len(data)} rows into {table}")

    print("Executing batch upserts into PostgreSQL...")
    execute_upsert("customers", "customer_id", customers)
    execute_upsert("products", "product_id", products)
    execute_upsert("orders", "order_id", orders)
    execute_upsert("order_items", "order_item_id", order_items)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Live PostgreSQL database seeded successfully!")


def main() -> None:
    parser = argparse.ArgumentParser(description="Distribute sources and generate DB seed script.")
    parser.add_argument("--seed-db", action="store_true", help="Seed the running PostgreSQL DB directly")
    args = parser.parse_args()

    print("🚀 Starting sources distribution and database setup...")

    # Load Parquet sources
    cust_df = pq.read_table(PARQUET_DIR / "customers.parquet").to_pandas()
    prod_df = pq.read_table(PARQUET_DIR / "products.parquet").to_pandas()
    ord_df = pq.read_table(PARQUET_DIR / "orders.parquet").to_pandas()
    items_df = pq.read_table(PARQUET_DIR / "order_items.parquet").to_pandas()

    print(f"Read sources: {len(cust_df)} customers, {len(prod_df)} products, {len(ord_df)} orders, {len(items_df)} order_items")

    customers = process_customers(cust_df)
    products = process_products(prod_df)
    orders = process_orders(ord_df)
    order_items = process_order_items(items_df)

    # 1. Generate SQL init script
    sql_init_path = SQL_DDL_DIR / "01_source_init.sql"
    generate_source_init_sql(customers, products, orders, order_items, sql_init_path)

    # 2. Combined Products Excel catalog
    excel_catalog_path = CATALOGS_DIR / "products_catalog.xlsx"
    overrides_csv = ROOT_DIR / "catalog_overrides.csv"
    create_combined_products_excel(products, overrides_csv, excel_catalog_path)

    # 3. Distribute logistics files (shipments & deliveries)
    distribute_logistics_files(
        PARQUET_DIR / "shipments.parquet",
        PARQUET_DIR / "deliveries.parquet",
        LOGISTICS_DIR,
    )

    # 4. Optional seed live database
    if args.seed_db:
        db_url = os.getenv("POSTGRES_SOURCE_URL", "postgresql://postgres:postgres@localhost:5436/saudi_ecom_orders")
        try:
            seed_running_postgres(customers, products, orders, order_items, db_url)
        except (psycopg2.Error, OSError) as err:
            print(f"⚠️ Could not seed live PostgreSQL database: {err}")

    print("🎉 All sources successfully distributed!")


if __name__ == "__main__":
    main()

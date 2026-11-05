"""Saudi eCommerce Synthetic Data Generator & Sources Loader.

Generates localized, high-fidelity synthetic eCommerce datasets for Saudi Arabia
and provides ingestion utilities to load, sanitize, and seed from external sources:
- Authentic Saudi customer identities (Arabic and English names, Saudi mobile numbers +9665XXXXXXXX).
- Regional distribution across provinces (Riyadh, Makkah/Jeddah, Eastern Province/Dammam, etc.).
- Product catalog with pricing strictly in integer Halalas (1 SAR = 100 Halalas).
- Orders, order items, and payment reconciliation events reflecting market payment methods
  (Mada 45%, Apple Pay 25%, Tabby/Tamara BNPL 15%, Cash on Delivery 15%).
- 15% Saudi Value Added Tax (VAT) calculation.
- Source dataset loading (Parquet, CSV, JSON, Excel) from `sources/`.
- Seeding utilities for local PostgreSQL databases and operational files (Excel/CSV).
"""

import json
import os
import random
import re
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

# Ensure project root is in sys.path when executed directly as a script
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from src.common.config import settings
from src.common.exceptions import PermanentError
from src.common.logging import generate_correlation_id, get_logger

logger = get_logger("synthetic_data_generator")

DEFAULT_SOURCES_DIR = Path(PROJECT_ROOT) / "sources"
ALL_SOURCE_ENTITIES = [
    "customers",
    "products",
    "orders",
    "order_items",
    "payments",
    "shipments",
    "deliveries",
]

DIGITS_REGEX = re.compile(r"\d+")
DATE_PREFIX_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}")

# Saudi Regional Data
SAUDI_REGIONS = [
    {
        "name_ar": "منطقة الرياض",
        "name_en": "Riyadh Region",
        "cities": ["Riyadh", "Al Kharj", "Diriyah"],
        "weight": 0.40,
    },
    {
        "name_ar": "منطقة مكة المكرمة",
        "name_en": "Makkah Region",
        "cities": ["Jeddah", "Mecca", "Taif"],
        "weight": 0.30,
    },
    {
        "name_ar": "المنطقة الشرقية",
        "name_en": "Eastern Province",
        "cities": ["Dammam", "Khobar", "Jubail", "Dhahran"],
        "weight": 0.18,
    },
    {
        "name_ar": "منطقة المدينة المنورة",
        "name_en": "Medina Region",
        "cities": ["Medina", "Yanbu"],
        "weight": 0.07,
    },
    {
        "name_ar": "منطقة عسير",
        "name_en": "Asir Region",
        "cities": ["Abha", "Khamis Mushait"],
        "weight": 0.05,
    },
]

# Authentic Saudi Names
FIRST_NAMES = [
    ("محمد", "Mohammed"),
    ("عبدالله", "Abdullah"),
    ("سعود", "Saud"),
    ("فهد", "Fahad"),
    ("سلطان", "Sultan"),
    ("خالد", "Khalid"),
    ("فيصل", "Faisal"),
    ("نورة", "Noura"),
    ("سارة", "Sara"),
    ("ريم", "Reem"),
    ("منى", "Mona"),
    ("هند", "Hind"),
    ("لطيفة", "Latifa"),
    ("شهد", "Shahad"),
    ("عمر", "Omar"),
]

LAST_NAMES = [
    ("الغامدي", "Al-Ghamdi"),
    ("القحطاني", "Al-Qahtani"),
    ("العتيبي", "Al-Otaibi"),
    ("الشمري", "Al-Shammari"),
    ("الدوسري", "Al-Dossary"),
    ("الشهري", "Al-Shehri"),
    ("الحربي", "Al-Harbi"),
    ("المطيري", "Al-Mutairi"),
    ("الزهراني", "Al-Zahrani"),
    ("العنزي", "Al-Anazi"),
]

# Product Catalog in Halalas (1 SAR = 100 Halalas)
SAUDI_PRODUCTS = [
    {"name_ar": "عطر العود الملكي فاخر 100 مل", "name_en": "Royal Oud Luxury Perfume 100ml", "category": "Fragrances", "price_sar": 450.00, "cost_sar": 220.00},
    {"name_ar": "بخور مروكي سوبر طبيعي 50 جم", "name_en": "Natural Super Maroki Incense 50g", "category": "Fragrances", "price_sar": 280.00, "cost_sar": 130.00},
    {"name_ar": "دلة قهوة عربية ستانلس ستيل", "name_en": "Traditional Arabic Coffee Dallah", "category": "Home", "price_sar": 195.00, "cost_sar": 85.00},
    {"name_ar": "سجادة صلاة فاخرة مبطنة", "name_en": "Premium Padded Prayer Mat", "category": "Home", "price_sar": 120.00, "cost_sar": 45.00},
    {"name_ar": "تمر خلاص الأحساء فاخر 1 كجم", "name_en": "Premium Al-Ahsa Khalas Dates 1kg", "category": "Groceries", "price_sar": 65.00, "cost_sar": 25.00},
    {"name_ar": "تمر سكري القصيم رطب 1 كجم", "name_en": "Qassim Fresh Sukari Dates 1kg", "category": "Groceries", "price_sar": 75.00, "cost_sar": 30.00},
    {"name_ar": "سماعة رأس لاسلكية إلغاء الضوضاء", "name_en": "Wireless Noise Cancelling Headphones", "category": "Electronics", "price_sar": 899.00, "cost_sar": 550.00},
    {"name_ar": "شاحن متنقل سريع 20,000 ملي أمبير", "name_en": "Fast Power Bank 20000mAh", "category": "Electronics", "price_sar": 189.00, "cost_sar": 95.00},
    {"name_ar": "ساعة يد ذكية مقاومة للماء", "name_en": "Smart Fitness Watch Waterproof", "category": "Electronics", "price_sar": 649.00, "cost_sar": 380.00},
    {"name_ar": "شماغ قطن كلاسيكي سعودي", "name_en": "Classic Saudi Cotton Shemagh", "category": "Fashion", "price_sar": 150.00, "cost_sar": 60.00},
    {"name_ar": "عباية نسائية سوداء كريب فاخرة", "name_en": "Luxury Black Crepe Women Abaya", "category": "Fashion", "price_sar": 340.00, "cost_sar": 140.00},
    {"name_ar": "ثوب رجالي سعودي أبيض مقلم", "name_en": "Traditional Saudi Men White Thobe", "category": "Fashion", "price_sar": 220.00, "cost_sar": 90.00},
]

# Market Payment Distribution in KSA
PAYMENT_METHODS = ["MADA", "APPLE_PAY", "TABBY", "TAMARA", "COD"]
PAYMENT_WEIGHTS = [0.45, 0.25, 0.10, 0.05, 0.15]

ORDER_STATUSES = ["DELIVERED", "SHIPPED", "PROCESSING", "PLACED", "CANCELLED"]
STATUS_WEIGHTS = [0.70, 0.12, 0.08, 0.06, 0.04]


def _clean_halalas_value(val: Any) -> int:
    """Extract and normalize positive integer Halalas from clean or corrupted input."""
    if pd.isna(val) or val is None:
        return 0
    if isinstance(val, int):
        return max(0, val)
    if isinstance(val, float):
        return max(0, round(val))
    digits_found = DIGITS_REGEX.findall(str(val))
    return int("".join(digits_found)) if digits_found else 0


def _clean_int_value(val: Any, default_val: int = 1) -> int:
    """Normalize integer count columns like quantity or attempt_number."""
    if pd.isna(val) or val is None:
        return default_val
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    digits_found = DIGITS_REGEX.findall(str(val))
    return int("".join(digits_found)) if digits_found else default_val


def _clean_bool_value(val: Any) -> bool:
    """Normalize boolean columns like is_cod."""
    if pd.isna(val) or val is None:
        return False
    if isinstance(val, bool):
        return val
    cleaned_str = str(val).strip().lower()
    return cleaned_str in ("true", "1", "t", "yes")


def _clean_id_value(val: Any, entity_prefix: str = "ID") -> str:
    """Normalize ID strings and replace empty or corrupt NULL values with unique identifiers."""
    if pd.isna(val) or val is None:
        return f"{entity_prefix}-{uuid.uuid4().hex[:12]}"
    cleaned_id = str(val).strip()
    if not cleaned_id or cleaned_id.upper() in ("NULL", "NONE", "NAN"):
        return f"{entity_prefix}-{uuid.uuid4().hex[:12]}"
    return cleaned_id


def _clean_timestamp_value(val: Any, default_iso: str | None = None) -> str | None:
    """Parse, normalize, and return ISO-8601 UTC timestamp string, filtering out lorem ipsum."""
    if pd.isna(val) or val is None:
        return default_iso
    cleaned_str = str(val).strip()
    if not cleaned_str or cleaned_str.upper() in ("NULL", "NONE", "NAN"):
        return default_iso
    if not DATE_PREFIX_REGEX.match(cleaned_str):
        return default_iso
    try:
        parsed_dt = datetime.fromisoformat(cleaned_str)
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=UTC)
        return parsed_dt.isoformat()
    except (ValueError, TypeError):
        try:
            pandas_dt = pd.to_datetime(cleaned_str, utc=True)
            if pd.isna(pandas_dt):
                return default_iso
            return cast(datetime, pandas_dt.to_pydatetime()).isoformat()
        except (ValueError, TypeError, OverflowError):
            return default_iso


class SaudiSyntheticGenerator:
    """High-fidelity localized synthetic data generator and sources ingestion engine."""

    def __init__(
        self,
        seed: int | None = 42,
        sources_dir: Path | str | None = None,
    ) -> None:
        if seed is not None:
            random.seed(seed)
        self.correlation_id = generate_correlation_id("gen_data")
        self.sources_dir: Path = (
            Path(sources_dir) if sources_dir is not None else DEFAULT_SOURCES_DIR
        )

    def get_sources_dir(self) -> Path | None:
        """Return the configured sources directory if it exists on disk, else None."""
        return self.sources_dir if self.sources_dir.exists() else None

    def get_available_source_entities(self, format: str = "parquet") -> list[str]:
        """Inspect source directory and list all available entities for the specified format."""
        norm_format = format.lower()
        if not self.sources_dir.exists():
            return []

        if norm_format == "parquet":
            parquet_files = list(self.sources_dir.glob("**/*.parquet"))
            return sorted({p.stem for p in parquet_files})
        elif norm_format == "csv":
            csv_files = list(self.sources_dir.glob("**/*.csv"))
            return sorted({c.stem for c in csv_files})
        elif norm_format == "json":
            json_files = sorted(self.sources_dir.glob("*data.json"))
            if json_files:
                try:
                    with open(json_files[0], "r", encoding="utf-8") as json_file:
                        data_payload = json.load(json_file)
                    if isinstance(data_payload, dict):
                        return sorted(data_payload.keys())
                except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc_err:
                    logger.warning(f"Could not read JSON entities from {json_files[0]}: {exc_err}")
            return [f.stem for f in self.sources_dir.glob("*.json")]
        elif norm_format in ("xlsx", "excel"):
            xlsx_files = sorted(self.sources_dir.glob("*data.xlsx"))
            if xlsx_files:
                try:
                    import openpyxl

                    workbook = openpyxl.load_workbook(xlsx_files[0], read_only=True)
                    return sorted(workbook.sheetnames)
                except (OSError, KeyError, ValueError) as exc_err:
                    logger.warning(
                        f"Could not inspect Excel sheet names from {xlsx_files[0]}: {exc_err}"
                    )
            return [f.stem for f in self.sources_dir.glob("*.xlsx")]
        return []

    def _get_source_file_path(self, entity: str, format: str) -> Path:
        """Resolve path to source dataset file based on entity and format."""
        norm_format = format.lower()
        if norm_format not in ("parquet", "csv", "json", "xlsx", "excel"):
            raise PermanentError(
                f"Unsupported source format '{format}'. Supported formats: parquet, csv, json, xlsx",
                id_correlation=self.correlation_id,
            )

        sources_path = self.sources_dir
        if not sources_path.exists():
            raise PermanentError(
                f"Sources directory not found at {sources_path}",
                id_correlation=self.correlation_id,
            )

        if norm_format == "parquet":
            candidate = sources_path / f"{entity}.parquet"
            if candidate.is_file():
                return candidate
            for parquet_dir in sorted(sources_path.glob("*parquet*")):
                if parquet_dir.is_dir():
                    candidate = parquet_dir / f"{entity}.parquet"
                    if candidate.is_file():
                        return candidate
            matches = list(sources_path.glob(f"**/{entity}.parquet"))
            if matches:
                return matches[0]

        elif norm_format == "csv":
            candidate = sources_path / f"{entity}.csv"
            if candidate.is_file():
                return candidate
            for csv_dir in sorted(sources_path.glob("*csv*")):
                if csv_dir.is_dir():
                    candidate = csv_dir / f"{entity}.csv"
                    if candidate.is_file():
                        return candidate
            matches = list(sources_path.glob(f"**/{entity}.csv"))
            if matches:
                return matches[0]

        elif norm_format == "json":
            candidate = sources_path / f"{entity}.json"
            if candidate.is_file():
                return candidate
            data_json_files = sorted(sources_path.glob("*data.json"))
            if data_json_files:
                return data_json_files[0]
            direct_json = sources_path / "data.json"
            if direct_json.is_file():
                return direct_json

        elif norm_format in ("xlsx", "excel"):
            data_xlsx_files = sorted(sources_path.glob("*data.xlsx"))
            if data_xlsx_files:
                return data_xlsx_files[0]
            candidate = sources_path / f"{entity}.xlsx"
            if candidate.is_file():
                return candidate

        raise PermanentError(
            f"Source entity '{entity}' not found in {sources_path} for format '{format}'.",
            id_correlation=self.correlation_id,
        )

    def load_source_table(
        self,
        entity: str,
        format: str = "parquet",
        sanitize: bool = False,
    ) -> pd.DataFrame:
        """Load source table DataFrame from Parquet, CSV, JSON, or Excel."""
        file_path = self._get_source_file_path(entity=entity, format=format)
        norm_format = format.lower()

        logger.info(
            f"Loading source table '{entity}' from {file_path.name} (format={format}, sanitize={sanitize})."
        )

        try:
            if norm_format == "parquet":
                df = pd.read_parquet(file_path)
            elif norm_format == "csv":
                df = pd.read_csv(file_path, dtype=str)
            elif norm_format == "json":
                with open(file_path, "r", encoding="utf-8") as json_file:
                    raw_data = json.load(json_file)
                if isinstance(raw_data, dict) and entity in raw_data:
                    df = pd.DataFrame(raw_data[entity])
                elif isinstance(raw_data, list):
                    df = pd.DataFrame(raw_data)
                else:
                    raise PermanentError(
                        f"Entity '{entity}' not present in JSON root keys",
                        id_correlation=self.correlation_id,
                    )
            elif norm_format in ("xlsx", "excel"):
                df = pd.read_excel(file_path, sheet_name=entity, dtype=str)
            else:
                raise PermanentError(
                    f"Unsupported source format '{format}'",
                    id_correlation=self.correlation_id,
                )
        except Exception as exc_err:
            if isinstance(exc_err, PermanentError):
                raise
            raise PermanentError(
                f"Failed to read source table '{entity}' from {file_path}: {exc_err}",
                id_correlation=self.correlation_id,
            ) from exc_err

        if sanitize:
            df = self.sanitize_source_table(entity=entity, df=df)

        return df

    def load_all_sources(
        self,
        format: str = "parquet",
        sanitize: bool = False,
    ) -> dict[str, pd.DataFrame]:
        """Load all available source entities into a dictionary of DataFrames."""
        available_entities = self.get_available_source_entities(format=format)
        loaded_tables: dict[str, pd.DataFrame] = {}
        for entity_name in available_entities:
            loaded_tables[entity_name] = self.load_source_table(
                entity=entity_name, format=format, sanitize=sanitize
            )
        logger.info(
            f"Loaded {len(loaded_tables)} source tables from {self.sources_dir} (format={format})."
        )
        return loaded_tables

    def sanitize_source_table(self, entity: str, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and normalize source table data for resilient enterprise consumption.

        - Strips whitespace from all textual columns and replaces 'NULL' with None.
        - Normalizes corrupted Halalas prices/costs to positive 64-bit integers.
        - Cleans quantities and attempt counters to valid integer bounds.
        - Sanitizes timestamps, substituting invalid/corrupted strings with valid UTC defaults.
        - Assigns valid identifiers to rows with missing or NULL primary keys.
        """
        df_clean = df.copy()

        # 1. Clean primary key column if present
        id_col = f"{entity[:-1]}_id" if entity.endswith("s") else f"{entity}_id"
        if id_col == "deliverie_id":
            id_col = "delivery_id"

        if id_col in df_clean.columns:
            prefix_tag = entity.upper()[:4]
            df_clean[id_col] = df_clean[id_col].apply(
                lambda val: _clean_id_value(val, entity_prefix=prefix_tag)
            )

        # 2. Clean numeric halalas columns
        for col_name in df_clean.columns:
            if col_name.endswith("_halalas"):
                df_clean[col_name] = df_clean[col_name].apply(_clean_halalas_value).astype("int64")
            elif col_name in ("quantity", "attempt_number"):
                df_clean[col_name] = df_clean[col_name].apply(_clean_int_value).astype("int32")
            elif col_name == "is_cod":
                df_clean[col_name] = df_clean[col_name].apply(_clean_bool_value).astype("bool")

        # 3. Clean timestamps
        default_base_iso = "2025-01-01T00:00:00+00:00"
        for col_name in df_clean.columns:
            if col_name in ("created_at", "updated_at"):
                df_clean[col_name] = df_clean[col_name].apply(
                    lambda val: _clean_timestamp_value(val, default_base_iso)
                )
                df_clean[col_name] = pd.to_datetime(df_clean[col_name], utc=True)
            elif col_name.endswith("_at"):
                df_clean[col_name] = df_clean[col_name].apply(
                    lambda val: _clean_timestamp_value(val, None)
                )
                df_clean[col_name] = pd.to_datetime(df_clean[col_name], utc=True)

        # 4. Strip string columns and replace 'NULL' / 'None' / empty strings with None
        for col_name in df_clean.columns:
            is_str_like = pd.api.types.is_string_dtype(
                df_clean[col_name]
            ) or df_clean[col_name].dtype == object
            is_dt = pd.api.types.is_datetime64_any_dtype(df_clean[col_name])
            is_num = pd.api.types.is_numeric_dtype(df_clean[col_name])
            if is_str_like and not is_dt and not is_num:
                df_clean[col_name] = df_clean[col_name].astype(str).str.strip()
                df_clean[col_name] = df_clean[col_name].replace(
                    {"NULL": None, "None": None, "nan": None, "": None}
                )

        return df_clean

    def enrich_catalog_from_sources(self, format: str = "parquet") -> bool:
        """Enrich in-memory product catalog and names using benchmark data in sources/."""
        if not self.sources_dir.exists():
            return False

        try:
            products_df = self.load_source_table("products", format=format, sanitize=True)
            for _, row in products_df.head(50).iterrows():
                product_dict = {
                    "name_ar": str(row["name_ar"]),
                    "name_en": str(row["name_en"]),
                    "category": str(row["category"]),
                    "price_sar": row["unit_price_halalas"] / 100.0,
                    "cost_sar": row["unit_cost_halalas"] / 100.0,
                }
                if not any(p["name_en"] == product_dict["name_en"] for p in SAUDI_PRODUCTS):
                    SAUDI_PRODUCTS.append(product_dict)

            customers_df = self.load_source_table("customers", format=format, sanitize=True)
            for _, row in customers_df.head(50).iterrows():
                name_ar_parts = str(row["name_ar"]).split()
                name_en_parts = str(row["name_en"]).split()
                if name_ar_parts and name_en_parts:
                    first_tuple = (name_ar_parts[0], name_en_parts[0])
                    if first_tuple not in FIRST_NAMES:
                        FIRST_NAMES.append(first_tuple)

            logger.info(
                f"Enriched catalog from sources ({format}): {len(SAUDI_PRODUCTS)} products available."
            )
            return True
        except (OSError, KeyError, ValueError, PermanentError) as exc_err:
            logger.warning(f"Could not enrich catalog from sources: {exc_err}")
            return False

    def generate_customers(self, count: int = 100) -> list[dict[str, Any]]:
        """Generate customer records with authentic Saudi names and addresses."""
        customers = []
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

        for customer_idx in range(1, count + 1):
            name_ar_tuple = random.choice(FIRST_NAMES)
            last_name_tuple = random.choice(LAST_NAMES)

            full_name_ar = f"{name_ar_tuple[0]} {last_name_tuple[0]}"
            full_name_en = f"{name_ar_tuple[1]} {last_name_tuple[1]}"

            # Weighted region selection
            region_weights = [cast(float, r["weight"]) for r in SAUDI_REGIONS]
            region: dict[str, Any] = random.choices(SAUDI_REGIONS, weights=region_weights, k=1)[0]
            city: str = random.choice(region["cities"])

            # Saudi phone number: +9665 + 8 random digits
            phone = f"+9665{random.randint(10000000, 99999999)}"
            email = f"{name_ar_tuple[1].lower()}.{last_name_tuple[1].lower()}{random.randint(10, 99)}@example.sa"

            created_days = random.randint(0, 365)
            created_at = base_time + timedelta(
                days=created_days, hours=random.randint(0, 23), minutes=random.randint(0, 59)
            )
            updated_at = created_at + timedelta(days=random.randint(0, 30))

            customers.append({
                "customer_id": f"CUST-{customer_idx:05d}",
                "name_ar": full_name_ar,
                "name_en": full_name_en,
                "email": email,
                "phone": phone,
                "region_ar": region["name_ar"],
                "region_en": region["name_en"],
                "city_en": city,
                "national_address": f"{random.randint(1000, 9999)} {city}, {region['name_en']}, KSA",
                "created_at": created_at.isoformat(),
                "updated_at": updated_at.isoformat(),
            })

        logger.info(f"Generated {len(customers)} synthetic Saudi customers.")
        return customers

    def generate_products(self) -> list[dict[str, Any]]:
        """Generate product catalog with Halalas integer pricing."""
        products = []
        for prod_idx, item in enumerate(SAUDI_PRODUCTS, start=1):
            unit_price_halalas = round(cast(float, item["price_sar"]) * 100)
            unit_cost_halalas = round(cast(float, item["cost_sar"]) * 100)

            products.append({
                "product_id": f"PROD-{prod_idx:04d}",
                "name_ar": item["name_ar"],
                "name_en": item["name_en"],
                "category": item["category"],
                "unit_price_halalas": unit_price_halalas,
                "unit_cost_halalas": unit_cost_halalas,
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
            })

        logger.info(f"Generated {len(products)} synthetic products.")
        return products

    def generate_transactions(
        self,
        customers: list[dict[str, Any]],
        products: list[dict[str, Any]],
        order_count: int = 500,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Generate orders, order items, and associated payment records."""
        orders = []
        order_items = []
        payments = []

        item_counter = 1
        payment_counter = 1

        for order_idx in range(1, order_count + 1):
            customer = random.choice(customers)
            order_id = f"ORD-{order_idx:06d}"

            # Number of line items in cart (1 to 4)
            num_items = random.choices([1, 2, 3, 4], weights=[0.50, 0.30, 0.15, 0.05], k=1)[0]
            selected_products = random.sample(products, k=min(num_items, len(products)))

            subtotal_halalas = 0
            order_items_list = []

            for product in selected_products:
                qty = random.choices([1, 2, 3], weights=[0.80, 0.15, 0.05], k=1)[0]
                unit_price = product["unit_price_halalas"]
                total_item_halalas = unit_price * qty
                subtotal_halalas += total_item_halalas

                item_record = {
                    "order_item_id": f"ITEM-{item_counter:07d}",
                    "order_id": order_id,
                    "product_id": product["product_id"],
                    "quantity": qty,
                    "unit_price_halalas": unit_price,
                    "unit_cost_halalas": product["unit_cost_halalas"],
                    "total_item_halalas": total_item_halalas,
                    "created_at": customer["created_at"],
                }
                order_items.append(item_record)
                order_items_list.append(item_record)
                item_counter += 1

            # 15% VAT on subtotal
            vat_halalas = round(subtotal_halalas * 0.15)

            # Flat shipping fee: free above 200 SAR (20000 Halalas), else 25 SAR (2500 Halalas)
            shipping_fee_halalas = 0 if subtotal_halalas >= 20000 else 2500

            # Promotional discount (optional 10% coupon applied 20% of the time)
            has_coupon = random.random() < 0.20
            coupon_code = "RAMADAN2026" if has_coupon else None
            discount_halalas = round(subtotal_halalas * 0.10) if has_coupon else 0

            total_halalas = subtotal_halalas - discount_halalas + vat_halalas + shipping_fee_halalas

            payment_method = random.choices(PAYMENT_METHODS, weights=PAYMENT_WEIGHTS, k=1)[0]
            status = random.choices(ORDER_STATUSES, weights=STATUS_WEIGHTS, k=1)[0]

            # Timing
            created_dt = datetime.fromisoformat(customer["created_at"]) + timedelta(
                days=random.randint(1, 180),
                hours=random.randint(0, 23),
            )
            updated_dt = created_dt + timedelta(hours=random.randint(2, 72))

            orders.append({
                "order_id": order_id,
                "customer_id": customer["customer_id"],
                "subtotal_halalas": subtotal_halalas,
                "vat_halalas": vat_halalas,
                "discount_halalas": discount_halalas,
                "shipping_fee_halalas": shipping_fee_halalas,
                "total_halalas": total_halalas,
                "coupon_code": coupon_code,
                "payment_method": payment_method,
                "status": status,
                "shipping_city": customer["city_en"],
                "shipping_region": customer["region_en"],
                "created_at": created_dt.isoformat(),
                "updated_at": updated_dt.isoformat(),
            })

            # Payment Settlement Record
            payment_status = (
                "SETTLED"
                if status in ["DELIVERED", "SHIPPED"]
                else ("REFUNDED" if status == "CANCELLED" else "PENDING")
            )
            settled_dt = updated_dt if payment_status == "SETTLED" else None

            payments.append({
                "payment_id": f"PAY-{payment_counter:06d}",
                "order_id": order_id,
                "payment_method": payment_method,
                "amount_halalas": total_halalas,
                "status": payment_status,
                "is_cod": (payment_method == "COD"),
                "gateway_reference": f"GW-{random.randint(1000000, 9999999)}",
                "settled_at": settled_dt.isoformat() if settled_dt else None,
                "created_at": created_dt.isoformat(),
            })
            payment_counter += 1

        logger.info(
            f"Generated {len(orders)} orders, {len(order_items)} items, and {len(payments)} payments."
        )
        return orders, order_items, payments

    def generate_operational_files(
        self,
        excel_path: str = "operational_sales_targets.xlsx",
        csv_path: str = "catalog_overrides.csv",
        use_sources: bool = False,
        format: str = "parquet",
    ) -> None:
        """Create sample operational files: Sales targets Excel workbook and Catalog overrides CSV.

        If use_sources is True, product overrides and targets are extracted from the source datasets.
        """
        if use_sources and self.sources_dir.exists():
            try:
                products_df = self.load_source_table("products", format=format, sanitize=True)
                top_products = products_df.head(5)
                overrides_data = {
                    "product_id": top_products["product_id"].tolist(),
                    "promotional_tag": [
                        "National Day Special",
                        "Best Seller",
                        "Tech Deal",
                        "Ramadan Offer",
                        "Exclusive Deal",
                    ][: len(top_products)],
                    "special_discount_pct": [15, 10, 20, 25, 10][: len(top_products)],
                }
                df_overrides = pd.DataFrame(overrides_data)
                df_overrides.to_csv(csv_path, index=False)
                logger.info(f"Created catalog overrides CSV from sources at {csv_path}")

                customers_df = self.load_source_table("customers", format=format, sanitize=True)
                regions = customers_df["region_en"].dropna().unique().tolist()[:5]
                targets_data = {
                    "Region": regions,
                    "Monthly_Target_SAR": [2500000, 1800000, 1200000, 450000, 350000][
                        : len(regions)
                    ],
                    "Quarterly_Target_SAR": [7500000, 5400000, 3600000, 1350000, 1050000][
                        : len(regions)
                    ],
                    "Delivery_SLA_Hours": [24, 24, 48, 72, 72][: len(regions)],
                }
                df_targets = pd.DataFrame(targets_data)
                df_targets.to_excel(excel_path, index=False)
                logger.info(
                    f"Created operational targets spreadsheet from sources at {excel_path}"
                )
                return
            except (OSError, KeyError, ValueError, PermanentError) as exc_err:
                logger.warning(
                    f"Could not generate operational files from sources: {exc_err}. Falling back to default synthetic files."
                )

        # Default fallback operational files
        targets_data = {
            "Region": [
                "Riyadh Region",
                "Makkah Region",
                "Eastern Province",
                "Medina Region",
                "Asir Region",
            ],
            "Monthly_Target_SAR": [2500000, 1800000, 1200000, 450000, 350000],
            "Quarterly_Target_SAR": [7500000, 5400000, 3600000, 1350000, 1050000],
            "Delivery_SLA_Hours": [24, 24, 48, 72, 72],
        }
        df_targets = pd.DataFrame(targets_data)
        df_targets.to_excel(excel_path, index=False)
        logger.info(f"Created operational targets spreadsheet at {excel_path}")

        overrides_data = {
            "product_id": ["PROD-0001", "PROD-0005", "PROD-0007"],
            "promotional_tag": ["Ramadan Special", "Best Seller", "Tech Deal"],
            "special_discount_pct": [15, 10, 20],
        }
        df_overrides = pd.DataFrame(overrides_data)
        df_overrides.to_csv(csv_path, index=False)
        logger.info(f"Created catalog overrides CSV at {csv_path}")

    def seed_postgres_from_sources(
        self,
        connection_url: str | None = None,
        format: str = "parquet",
        sanitize: bool = True,
        batch_size: int = 1000,
    ) -> bool:
        """Seed PostgreSQL database from source datasets with resilient schema mapping."""
        url = connection_url or settings.postgres_connection_url
        engine = create_engine(url)

        try:
            with engine.connect() as conn:
                logger.info(
                    f"Connected to PostgreSQL at {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db} to seed from sources."
                )

                # Clean drop in reverse topological order
                conn.execute(text("""
                    DROP TABLE IF EXISTS deliveries CASCADE;
                    DROP TABLE IF EXISTS shipments CASCADE;
                    DROP TABLE IF EXISTS payments CASCADE;
                    DROP TABLE IF EXISTS order_items CASCADE;
                    DROP TABLE IF EXISTS orders CASCADE;
                    DROP TABLE IF EXISTS products CASCADE;
                    DROP TABLE IF EXISTS customers CASCADE;
                """))
                conn.commit()

                # Flexible DDL matching source data structure
                conn.execute(text("""
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
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS products (
                        product_id VARCHAR(64) PRIMARY KEY,
                        name_ar TEXT NOT NULL,
                        name_en TEXT NOT NULL,
                        category TEXT NOT NULL,
                        unit_price_halalas BIGINT NOT NULL,
                        unit_cost_halalas BIGINT NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE NOT NULL
                    );

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
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS order_items (
                        order_item_id VARCHAR(64) PRIMARY KEY,
                        order_id VARCHAR(64) NOT NULL,
                        product_id VARCHAR(64) NOT NULL,
                        quantity INT NOT NULL,
                        unit_price_halalas BIGINT NOT NULL,
                        unit_cost_halalas BIGINT NOT NULL,
                        total_item_halalas BIGINT NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS payments (
                        payment_id VARCHAR(64) PRIMARY KEY,
                        order_id VARCHAR(64) NOT NULL,
                        payment_method TEXT NOT NULL,
                        amount_halalas BIGINT NOT NULL,
                        status TEXT NOT NULL,
                        is_cod BOOLEAN NOT NULL,
                        gateway_reference TEXT,
                        settled_at TIMESTAMP WITH TIME ZONE,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS shipments (
                        shipment_id VARCHAR(64) PRIMARY KEY,
                        order_id VARCHAR(64) NOT NULL,
                        carrier_name TEXT NOT NULL,
                        tracking_number TEXT,
                        shipping_method TEXT NOT NULL,
                        status TEXT NOT NULL,
                        origin_city TEXT,
                        destination_city TEXT NOT NULL,
                        destination_region TEXT NOT NULL,
                        shipping_fee_halalas BIGINT NOT NULL,
                        shipped_at TIMESTAMP WITH TIME ZONE,
                        estimated_delivery_at TIMESTAMP WITH TIME ZONE,
                        delivered_at TIMESTAMP WITH TIME ZONE,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS deliveries (
                        delivery_id VARCHAR(64) PRIMARY KEY,
                        shipment_id VARCHAR(64) NOT NULL,
                        attempt_number INT NOT NULL,
                        status TEXT NOT NULL,
                        recipient_name TEXT,
                        recipient_phone TEXT,
                        delivery_city TEXT NOT NULL,
                        delivery_address TEXT NOT NULL,
                        failure_reason TEXT,
                        scheduled_at TIMESTAMP WITH TIME ZONE,
                        attempted_at TIMESTAMP WITH TIME ZONE,
                        completed_at TIMESTAMP WITH TIME ZONE,
                        proof_of_delivery_url TEXT,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE NOT NULL
                    );
                """))
                conn.commit()

            tables_to_seed = [
                "customers",
                "products",
                "orders",
                "order_items",
                "payments",
                "shipments",
                "deliveries",
            ]
            for entity_name in tables_to_seed:
                df_table = self.load_source_table(
                    entity=entity_name, format=format, sanitize=sanitize
                )
                id_col = (
                    f"{entity_name[:-1]}_id" if entity_name.endswith("s") else f"{entity_name}_id"
                )
                if id_col == "deliverie_id":
                    id_col = "delivery_id"
                if id_col in df_table.columns:
                    df_table = df_table.drop_duplicates(subset=[id_col], keep="first")

                df_table.to_sql(
                    entity_name,
                    engine,
                    if_exists="append",
                    index=False,
                    chunksize=batch_size,
                    method="multi",
                )
                logger.info(f"Seeded {len(df_table)} rows into table '{entity_name}'.")

            logger.info("Successfully seeded all 7 source tables into PostgreSQL.")
            return True
        except (OSError, SQLAlchemyError) as exc_err:
            logger.warning(
                f"Could not connect to live PostgreSQL: {exc_err}. (This is normal when running outside container)"
            )
            return False

    def seed_postgres(
        self,
        connection_url: str | None = None,
        customer_count: int = 100,
        order_count: int = 500,
        use_sources: bool = False,
        format: str = "parquet",
    ) -> bool:
        """Seed local PostgreSQL database with generated tables or from source datasets."""
        if use_sources:
            return self.seed_postgres_from_sources(
                connection_url=connection_url,
                format=format,
                sanitize=True,
            )

        url = connection_url or settings.postgres_connection_url
        engine = create_engine(url)

        try:
            with engine.connect() as conn:
                logger.info(
                    f"Connected to PostgreSQL at {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
                )

                # Clean drop in reverse dependency order
                conn.execute(text("""
                    DROP TABLE IF EXISTS order_items CASCADE;
                    DROP TABLE IF EXISTS orders CASCADE;
                    DROP TABLE IF EXISTS products CASCADE;
                    DROP TABLE IF EXISTS customers CASCADE;
                """))
                conn.commit()

                # Create schema DDL
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS customers (
                        customer_id VARCHAR(32) PRIMARY KEY,
                        name_ar VARCHAR(255) NOT NULL,
                        name_en VARCHAR(255) NOT NULL,
                        email VARCHAR(255) NOT NULL,
                        phone VARCHAR(32) NOT NULL,
                        region_ar VARCHAR(128) NOT NULL,
                        region_en VARCHAR(128) NOT NULL,
                        city_en VARCHAR(128) NOT NULL,
                        national_address TEXT NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS products (
                        product_id VARCHAR(32) PRIMARY KEY,
                        name_ar VARCHAR(255) NOT NULL,
                        name_en VARCHAR(255) NOT NULL,
                        category VARCHAR(128) NOT NULL,
                        unit_price_halalas BIGINT NOT NULL,
                        unit_cost_halalas BIGINT NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS orders (
                        order_id VARCHAR(32) PRIMARY KEY,
                        customer_id VARCHAR(32) REFERENCES customers(customer_id),
                        subtotal_halalas BIGINT NOT NULL,
                        vat_halalas BIGINT NOT NULL,
                        discount_halalas BIGINT NOT NULL,
                        shipping_fee_halalas BIGINT NOT NULL,
                        total_halalas BIGINT NOT NULL,
                        coupon_code VARCHAR(64),
                        payment_method VARCHAR(32) NOT NULL,
                        status VARCHAR(32) NOT NULL,
                        shipping_city VARCHAR(128) NOT NULL,
                        shipping_region VARCHAR(128) NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS order_items (
                        order_item_id VARCHAR(32) PRIMARY KEY,
                        order_id VARCHAR(32) REFERENCES orders(order_id),
                        product_id VARCHAR(32) REFERENCES products(product_id),
                        quantity INT NOT NULL,
                        unit_price_halalas BIGINT NOT NULL,
                        unit_cost_halalas BIGINT NOT NULL,
                        total_item_halalas BIGINT NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL
                    );
                """))
                conn.commit()

            # Generate data
            customers = self.generate_customers(count=customer_count)
            products = self.generate_products()
            orders, order_items, _ = self.generate_transactions(
                customers=customers, products=products, order_count=order_count
            )

            # Insert via pandas for clean type mapping
            df_customers = pd.DataFrame(customers)
            df_products = pd.DataFrame(products)
            df_orders = pd.DataFrame(orders)
            df_order_items = pd.DataFrame(order_items)

            df_customers.to_sql("customers", engine, if_exists="append", index=False)
            df_products.to_sql("products", engine, if_exists="append", index=False)
            df_orders.to_sql("orders", engine, if_exists="append", index=False)
            df_order_items.to_sql("order_items", engine, if_exists="append", index=False)

            logger.info(
                "Successfully seeded customers, products, orders, and order_items to PostgreSQL."
            )
            return True
        except (OSError, SQLAlchemyError) as exc_err:
            logger.warning(
                f"Could not connect to live PostgreSQL: {exc_err}. (This is normal when running outside container)"
            )
            return False


if __name__ == "__main__":
    generator = SaudiSyntheticGenerator(seed=42)
    sources_directory = generator.get_sources_dir()
    if sources_directory and sources_directory.exists():
        print(f"Sources directory found at: {sources_directory}")
        entities = generator.get_available_source_entities(format="parquet")
        print(f"Discovered source entities: {entities}")
        generator.enrich_catalog_from_sources(format="parquet")
        generator.generate_operational_files(use_sources=True)
        generator.seed_postgres(use_sources=True, format="parquet")
    else:
        # Generate operational sample files
        generator.generate_operational_files()
        # Attempt seeding if database is reachable
        generator.seed_postgres()

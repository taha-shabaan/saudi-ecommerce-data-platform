"""Saudi eCommerce Synthetic Data Generator.

Generates localized, high-fidelity synthetic eCommerce datasets for Saudi Arabia:
- Authentic Saudi customer identities (Arabic and English names, Saudi mobile numbers +9665XXXXXXXX).
- Regional distribution across provinces (Riyadh, Makkah/Jeddah, Eastern Province/Dammam, etc.).
- Product catalog with pricing strictly in integer Halalas (1 SAR = 100 Halalas).
- Orders, order items, and payment reconciliation events reflecting market payment methods
  (Mada 45%, Apple Pay 25%, Tabby/Tamara BNPL 15%, Cash on Delivery 15%).
- 15% Saudi Value Added Tax (VAT) calculation.
- Seeding utilities for local PostgreSQL databases and operational files (Excel/CSV).
"""

from datetime import datetime, timedelta, timezone
import os
import random
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is in sys.path when executed directly as a script
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
from sqlalchemy import create_engine, text
from src.common.config import settings
from src.common.logging import generate_correlation_id, get_logger

logger = get_logger("synthetic_data_generator")

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


class SaudiSyntheticGenerator:
    """High-fidelity localized synthetic data generator for the Saudi eCommerce Platform."""

    def __init__(self, seed: Optional[int] = 42) -> None:
        if seed is not None:
            random.seed(seed)
        self.correlation_id = generate_correlation_id("gen_data")

    def generate_customers(self, count: int = 100) -> List[Dict[str, Any]]:
        """Generate customer records with authentic Saudi names and addresses."""
        customers = []
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        for i in range(1, count + 1):
            name_ar_tuple = random.choice(FIRST_NAMES)
            last_name_tuple = random.choice(LAST_NAMES)

            full_name_ar = f"{name_ar_tuple[0]} {last_name_tuple[0]}"
            full_name_en = f"{name_ar_tuple[1]} {last_name_tuple[1]}"

            # Weighted region selection
            region_weights = [r["weight"] for r in SAUDI_REGIONS]
            region = random.choices(SAUDI_REGIONS, weights=region_weights, k=1)[0]
            city = random.choice(region["cities"])

            # Saudi phone number: +9665 + 8 random digits
            phone = f"+9665{random.randint(10000000, 99999999)}"
            email = f"{name_ar_tuple[1].lower()}.{last_name_tuple[1].lower()}{random.randint(10, 99)}@example.sa"

            created_days = random.randint(0, 365)
            created_at = base_time + timedelta(days=created_days, hours=random.randint(0, 23), minutes=random.randint(0, 59))
            updated_at = created_at + timedelta(days=random.randint(0, 30))

            customers.append({
                "customer_id": f"CUST-{i:05d}",
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

    def generate_products(self) -> List[Dict[str, Any]]:
        """Generate product catalog with Halalas integer pricing."""
        products = []
        for i, item in enumerate(SAUDI_PRODUCTS, start=1):
            unit_price_halalas = int(round(item["price_sar"] * 100))
            unit_cost_halalas = int(round(item["cost_sar"] * 100))

            products.append({
                "product_id": f"PROD-{i:04d}",
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
        customers: List[Dict[str, Any]],
        products: List[Dict[str, Any]],
        order_count: int = 500,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Generate orders, order items, and associated payment records."""
        orders = []
        order_items = []
        payments = []

        item_counter = 1
        payment_counter = 1

        for o_idx in range(1, order_count + 1):
            customer = random.choice(customers)
            order_id = f"ORD-{o_idx:06d}"

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
            vat_halalas = int(round(subtotal_halalas * 0.15))

            # Flat shipping fee: free above 200 SAR (20000 Halalas), else 25 SAR (2500 Halalas)
            shipping_fee_halalas = 0 if subtotal_halalas >= 20000 else 2500

            # Promotional discount (optional 10% coupon applied 20% of the time)
            has_coupon = random.random() < 0.20
            coupon_code = "RAMADAN2026" if has_coupon else None
            discount_halalas = int(round(subtotal_halalas * 0.10)) if has_coupon else 0

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
            payment_status = "SETTLED" if status in ["DELIVERED", "SHIPPED"] else ("REFUNDED" if status == "CANCELLED" else "PENDING")
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

        logger.info(f"Generated {len(orders)} orders, {len(order_items)} items, and {len(payments)} payments.")
        return orders, order_items, payments

    def generate_operational_files(
        self,
        excel_path: str = "operational_sales_targets.xlsx",
        csv_path: str = "catalog_overrides.csv",
    ) -> None:
        """Create sample operational files: Sales targets Excel workbook and Catalog overrides CSV."""
        # Operational targets
        targets_data = {
            "Region": ["Riyadh Region", "Makkah Region", "Eastern Province", "Medina Region", "Asir Region"],
            "Monthly_Target_SAR": [2500000, 1800000, 1200000, 450000, 350000],
            "Quarterly_Target_SAR": [7500000, 5400000, 3600000, 1350000, 1050000],
            "Delivery_SLA_Hours": [24, 24, 48, 72, 72],
        }
        df_targets = pd.DataFrame(targets_data)
        df_targets.to_excel(excel_path, index=False)
        logger.info(f"Created operational targets spreadsheet at {excel_path}")

        # Catalog overrides CSV
        overrides_data = {
            "product_id": ["PROD-0001", "PROD-0005", "PROD-0007"],
            "promotional_tag": ["Ramadan Special", "Best Seller", "Tech Deal"],
            "special_discount_pct": [15, 10, 20],
        }
        df_overrides = pd.DataFrame(overrides_data)
        df_overrides.to_csv(csv_path, index=False)
        logger.info(f"Created catalog overrides CSV at {csv_path}")

    def seed_postgres(
        self,
        connection_url: Optional[str] = None,
        customer_count: int = 100,
        order_count: int = 500,
    ) -> bool:
        """Seed local PostgreSQL database with generated tables and records."""
        url = connection_url or settings.postgres_connection_url
        engine = create_engine(url)

        try:
            with engine.connect() as conn:
                logger.info(f"Connected to PostgreSQL at {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}")

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

            logger.info("Successfully seeded customers, products, orders, and order_items to PostgreSQL.")
            return True
        except Exception as exc:
            logger.warning(f"Could not connect to live PostgreSQL: {exc}. (This is normal when running outside container)")
            return False


if __name__ == "__main__":
    generator = SaudiSyntheticGenerator(seed=42)
    # Generate operational sample files
    generator.generate_operational_files()
    # Attempt seeding if database is reachable
    generator.seed_postgres()

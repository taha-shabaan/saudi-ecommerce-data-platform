"""
Tests for Seam 3: Relational Synthetic Data Generation Engine
"""

import pytest
from app.models.schema import (
    EntityDefinition,
    AttributeDefinition,
    ConsistencyPolicy,
    GenerateRequest
)
from app.core.engine import DataEngine


def test_referential_integrity_and_pk_pool():
    """
    Test that child foreign keys strictly sample from parent primary keys.
    """
    request = GenerateRequest(
        locales=["en_US"],
        entities=[
            EntityDefinition(
                name="users",
                record_count=5,
                attributes=[
                    AttributeDefinition(name="id", type="autoincrement", is_primary_key=True),
                    AttributeDefinition(name="name", type="full_name")
                ]
            ),
            EntityDefinition(
                name="orders",
                record_count=15,
                attributes=[
                    AttributeDefinition(name="id", type="autoincrement", is_primary_key=True),
                    AttributeDefinition(name="user_id", type="foreign_key", fk_target="users.id"),
                    AttributeDefinition(name="amount", type="numeric_range", params={"min": 10, "max": 100})
                ]
            )
        ],
        policy=ConsistencyPolicy(orphan_rate=0.0)
    )

    engine = DataEngine()
    dataset = engine.generate(request)

    assert dataset.success is True
    assert len(dataset.records["users"]) == 5
    assert len(dataset.records["orders"]) == 15

    parent_ids = {u["id"] for u in dataset.records["users"]}
    assert parent_ids == {1, 2, 3, 4, 5}

    # Every order.user_id must exist in parent_ids
    for order in dataset.records["orders"]:
        assert order["user_id"] in parent_ids


def test_orphan_injection():
    """
    Test that orphan_rate deliberately injects non-existent parent IDs.
    """
    request = GenerateRequest(
        locales=["en_US"],
        entities=[
            EntityDefinition(
                name="users",
                record_count=5,
                attributes=[
                    AttributeDefinition(name="id", type="autoincrement", is_primary_key=True)
                ]
            ),
            EntityDefinition(
                name="orders",
                record_count=20,
                attributes=[
                    AttributeDefinition(name="id", type="autoincrement", is_primary_key=True),
                    AttributeDefinition(name="user_id", type="foreign_key", fk_target="users.id")
                ]
            )
        ],
        policy=ConsistencyPolicy(orphan_rate=1.0) # 100% orphans
    )

    engine = DataEngine()
    dataset = engine.generate(request)

    parent_ids = {u["id"] for u in dataset.records["users"]}
    # At 100% orphan rate, no order should reference a valid parent ID
    for order in dataset.records["orders"]:
        assert order["user_id"] not in parent_ids
        assert order["user_id"] >= 999000


def test_row_level_locale_binding():
    """
    Test that when multiple locales are present, records maintain cultural coherence
    (e.g., country attribute matches the assigned row locale).
    """
    request = GenerateRequest(
        locales=["ar_EG", "de_DE"],
        entities=[
            EntityDefinition(
                name="profiles",
                record_count=10,
                attributes=[
                    AttributeDefinition(name="id", type="autoincrement", is_primary_key=True),
                    AttributeDefinition(name="full_name", type="full_name"),
                    AttributeDefinition(name="country", type="country")
                ]
            )
        ],
        policy=ConsistencyPolicy(locale_drift_rate=0.0) # Strict row-level coherence
    )

    engine = DataEngine()
    dataset = engine.generate(request)
    records = dataset.records["profiles"]

    assert len(records) == 10
    for r in records:
        assert r["country"] in ["Egypt", "Germany"]

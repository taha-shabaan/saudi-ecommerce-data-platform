"""
Tests for the Saved Schema Registry (ADRs: docs/adr/0001-sqlite-schema-registry.md).
Seam under test: REST /api/v1/schemas (pre-agreed). SchemaRegistry is exercised
directly only for restart-survivability, which HTTP cannot express.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app as fastapi_app

SNAPSHOT = {
    "name": "ecommerce_core",
    "locales": ["ar_EG"],
    "entities": [
        {
            "name": "customers",
            "record_count": 5,
            "attributes": [
                {"name": "id", "type": "autoincrement", "is_primary_key": True},
                {"name": "email", "type": "email"},
            ],
        }
    ],
    "policy": {
        "preset": "strict",
        "orphan_rate": 0.0,
        "locale_drift_rate": 0.0,
        "noise_rate": 0.0,
        "duplicate_rate": 0.0,
    },
    "sinks": {"postgres": True},
}


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("SCHEMA_REGISTRY_DB", str(tmp_path / "registry.db"))
    from app.core.schema_registry import reset_cached_registry
    reset_cached_registry()
    return TestClient(fastapi_app)


def _save_body(name="ecommerce_core", origin="dbml_import", snapshot=None):
    return {
        "name": name,
        "origin": origin,
        "dbml_source": "Table customers { id int [pk] }" if origin == "dbml_import" else None,
        "snapshot": snapshot if snapshot is not None else SNAPSHOT,
    }


def test_save_then_get_roundtrip(client):
    response = client.post("/api/v1/schemas", json=_save_body())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "ecommerce_core"
    assert body["status"] == "created"

    fetched = client.get("/api/v1/schemas/ecommerce_core")
    assert fetched.status_code == 200
    full = fetched.json()
    assert full["name"] == "ecommerce_core"
    assert full["origin"] == "dbml_import"
    assert full["dbml_source"] == "Table customers { id int [pk] }"
    assert full["snapshot"] == SNAPSHOT


def test_list_returns_metadata_not_snapshot(client):
    client.post("/api/v1/schemas", json=_save_body())
    client.post("/api/v1/schemas", json=_save_body(name="payments_flow", origin="canvas"))

    listing = client.get("/api/v1/schemas")
    assert listing.status_code == 200
    items = listing.json()["schemas"]
    names = {item["name"] for item in items}
    assert names == {"ecommerce_core", "payments_flow"}

    for item in items:
        assert set(item.keys()) == {
            "name", "origin", "entity_count", "created_at", "updated_at"
        }
        assert "snapshot" not in item
        assert "dbml_source" not in item
        assert item["entity_count"] >= 1
        assert "T" in item["created_at"]  # ISO 8601 timestamp


def test_upsert_overwrites_same_name(client):
    first = client.post("/api/v1/schemas", json=_save_body())
    assert first.json()["status"] == "created"

    modified = dict(SNAPSHOT)
    modified["entities"] = [SNAPSHOT["entities"][0]] + [
        {"name": "orders", "record_count": 3,
         "attributes": [{"name": "id", "type": "autoincrement", "is_primary_key": True}]}
    ]
    second = client.post("/api/v1/schemas", json=_save_body(snapshot=modified))
    assert second.status_code == 200
    assert second.json()["status"] == "updated"

    items = client.get("/api/v1/schemas").json()["schemas"]
    assert len(items) == 1
    assert items[0]["entity_count"] == 2

    fetched = client.get("/api/v1/schemas/ecommerce_core").json()
    assert len(fetched["snapshot"]["entities"]) == 2
    assert fetched["updated_at"] >= fetched["created_at"]


def test_save_rejects_blank_name(client):
    response = client.post("/api/v1/schemas", json=_save_body(name="   "))
    assert response.status_code == 422


def test_get_unknown_schema_returns_404(client):
    assert client.get("/api/v1/schemas/never_saved").status_code == 404


def test_delete_roundtrip(client):
    client.post("/api/v1/schemas", json=_save_body())

    assert client.delete("/api/v1/schemas/ecommerce_core").status_code == 204
    assert client.get("/api/v1/schemas/ecommerce_core").status_code == 404
    assert client.delete("/api/v1/schemas/ecommerce_core").status_code == 404


def test_registry_survives_reconnection(tmp_path, monkeypatch):
    """Saved schemas must live on disk, not process memory (restart safety)."""
    monkeypatch.setenv("SCHEMA_REGISTRY_DB", str(tmp_path / "registry.db"))
    from app.core.schema_registry import get_registry, reset_cached_registry
    reset_cached_registry()

    registry_now = get_registry()
    registry_now.upsert(name="persist_me", origin="canvas", dbml_source=None, snapshot=SNAPSHOT)

    reset_cached_registry()  # simulate process restart
    registry_restarted = get_registry()
    fetched = registry_restarted.get("persist_me")
    assert fetched is not None
    assert fetched["snapshot"] == SNAPSHOT

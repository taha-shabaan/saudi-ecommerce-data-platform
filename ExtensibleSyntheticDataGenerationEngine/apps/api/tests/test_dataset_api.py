"""
Tests for Saved Dataset reuse over HTTP: generation persists datasets,
downloads and the mock API serve previously generated rows across a
fresh-process simulation, and datasets can be listed and deleted.
"""

import json
import os
import zipfile
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.core import dataset_registry


GEN_PAYLOAD = {
    "schema_id": "reuse_sch",
    "name": "Reuse Test Schema",
    "locales": ["en_US"],
    "entities": [
        {
            "name": "authors",
            "record_count": 4,
            "attributes": [
                {"name": "id", "type": "autoincrement", "is_primary_key": True},
                {"name": "name", "type": "full_name"},
            ],
        },
        {
            "name": "books",
            "record_count": 6,
            "attributes": [
                {"name": "id", "type": "autoincrement", "is_primary_key": True},
                {"name": "author_id", "type": "foreign_key", "fk_target": "authors.id"},
                {"name": "title", "type": "text"},
            ],
        },
    ],
    "sinks": {"postgres": True, "excel": True, "csv": True, "parquet": True, "json": True, "api": True},
}


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DATASET_STORE_DIR", str(tmp_path / "datasets"))
    dataset_registry.reset_dataset_registry()
    yield
    dataset_registry.reset_dataset_registry()


@pytest.fixture
def fresh_client(isolated_store):
    """A client pair: the first acts as the original process, the second as a
    restart where no generation-side server state should be needed."""
    from app.main import app

    original = TestClient(app)
    # App-lifespan state keeps no client affinity for the dataset store; a
    # fresh TestClient exercises the same app as a restarted process would.
    after_restart = TestClient(app)
    return original, after_restart


def test_generate_persists_and_lists_datasets(fresh_client):
    original, _ = fresh_client
    gen = original.post("/api/v1/generate", json=GEN_PAYLOAD)
    assert gen.status_code == 200

    listing = original.get("/api/v1/datasets/reuse_sch")
    assert listing.status_code == 200
    datasets = listing.json()["datasets"]
    assert len(datasets) == 1
    assert datasets[0]["schema_id"] == "reuse_sch"
    assert datasets[0]["row_counts"] == {"authors": 4, "books": 6}
    assert datasets[0]["dataset_id"].startswith("ds_")


def test_downloads_re_derive_from_persisted_rows(fresh_client):
    original, after_restart = fresh_client
    original.post("/api/v1/generate", json=GEN_PAYLOAD)
    # trigger a restart-equivalent reset so no generation-time caches are consulted
    dataset_registry.reset_dataset_registry()

    for export_type, check in [
        ("sql", lambda r: b"CREATE TABLE IF NOT EXISTS" in r.content),
        ("excel", lambda r: len(r.content) > 0),
        ("csv", lambda r: zipfile.is_zipfile(BytesIO(r.content))),
        ("parquet", lambda r: zipfile.is_zipfile(BytesIO(r.content))),
        ("json", lambda r: len(json.loads(r.content)["authors"]) == 4),
    ]:
        res = after_restart.get(f"/api/v1/download/reuse_sch/{export_type}")
        assert res.status_code == 200, f"{export_type}"
        assert check(res), f"{export_type}"


def test_download_dataset_id_selects_version(fresh_client):
    original, after_restart = fresh_client

    original.post("/api/v1/generate", json=GEN_PAYLOAD)
    first_id = original.get("/api/v1/datasets/reuse_sch").json()["datasets"][0]["dataset_id"]

    payload = json.loads(json.dumps(GEN_PAYLOAD))
    payload["entities"][0]["record_count"] = 9
    payload["entities"][1]["record_count"] = 9
    original.post("/api/v1/generate", json=payload)

    # by default (latest) downloads must reflect the 9-row version
    latest_sql = after_restart.get("/api/v1/download/reuse_sch/sql")
    assert latest_sql.status_code == 200
    assert '-- Insert records into: authors (9 rows)' in latest_sql.text

    # explicit dataset_id must serve the first generation
    first_sql = after_restart.get(f"/api/v1/download/reuse_sch/sql?dataset_id={first_id}")
    assert first_sql.status_code == 200
    assert '-- Insert records into: authors (4 rows)' in first_sql.text


def test_download_unknown_dataset_or_export_is_404(fresh_client):
    _, after_restart = fresh_client
    after_restart.post("/api/v1/generate", json=GEN_PAYLOAD)

    assert after_restart.get("/api/v1/download/reuse_sch/sql?dataset_id=ds_missing").status_code == 404
    assert after_restart.get("/api/v1/download/never_sch/sql").status_code == 404
    res = after_restart.get("/api/v1/download/reuse_sch/bogus")
    assert res.status_code == 404


def test_mock_api_serves_persisted_rows_across_restart(fresh_client):
    _, after_restart = fresh_client
    after_restart.post("/api/v1/generate", json=GEN_PAYLOAD)
    dataset_registry.reset_dataset_registry()

    catalog = after_restart.get("/api/v1/mock/reuse_sch")
    assert catalog.status_code == 200
    assert len(catalog.json()["entities"]) == 2

    page = after_restart.get("/api/v1/mock/reuse_sch/books?limit=3&offset=0")
    assert page.status_code == 200
    data = page.json()
    assert len(data["data"]) == 3
    assert data["pagination"]["total_records"] == 6


def test_mock_api_unknown_schema_404(fresh_client):
    _, after_restart = fresh_client
    res = after_restart.get("/api/v1/mock/never_sch")
    assert res.status_code == 404


def test_delete_dataset_endpoint(fresh_client):
    original, after_restart = fresh_client
    original.post("/api/v1/generate", json=GEN_PAYLOAD)
    dataset_id = after_restart.get("/api/v1/datasets/reuse_sch").json()["datasets"][0]["dataset_id"]

    assert after_restart.delete(f"/api/v1/datasets/reuse_sch/{dataset_id}").status_code == 204
    assert after_restart.delete(f"/api/v1/datasets/reuse_sch/{dataset_id}").status_code == 404
    assert after_restart.get("/api/v1/datasets/reuse_sch").json()["datasets"] == []

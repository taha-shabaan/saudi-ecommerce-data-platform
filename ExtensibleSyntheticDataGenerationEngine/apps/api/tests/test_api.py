"""
Tests for Seam 5: FastAPI HTTP API Endpoints
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_list_generators_endpoint():
    response = client.get("/api/v1/generators")
    assert response.status_code == 200
    data = response.json()
    assert "generators" in data
    assert len(data["generators"]) > 5
    assert any(g["name"] == "full_name" for g in data["generators"])


def test_generate_and_mock_api_flow():
    payload = {
        "schema_id": "test_e2e_sch",
        "name": "E2E Test Schema",
        "locales": ["en_US"],
        "entities": [
            {
                "name": "authors",
                "record_count": 4,
                "attributes": [
                    {"name": "id", "type": "autoincrement", "is_primary_key": True},
                    {"name": "name", "type": "full_name"}
                ]
            },
            {
                "name": "books",
                "record_count": 6,
                "attributes": [
                    {"name": "id", "type": "autoincrement", "is_primary_key": True},
                    {"name": "author_id", "type": "foreign_key", "fk_target": "authors.id"},
                    {"name": "title", "type": "text"}
                ]
            }
        ],
        "policy": {
            "preset": "strict",
            "orphan_rate": 0.0,
            "locale_drift_rate": 0.0,
            "noise_rate": 0.0,
            "duplicate_rate": 0.0
        },
        "sinks": {
            "postgres": True,
            "excel": True,
            "csv": True,
            "parquet": True,
            "json": True,
            "api": True
        }
    }

    # 1. Generate dataset
    gen_res = client.post("/api/v1/generate", json=payload)
    assert gen_res.status_code == 200
    body = gen_res.json()
    assert body["status"] == "success"
    assert body["execution_order"] == ["authors", "books"]
    assert "artifacts" in body

    # 2. Check Mock API Catalog
    cat_res = client.get("/api/v1/mock/test_e2e_sch")
    assert cat_res.status_code == 200
    cat_data = cat_res.json()
    assert len(cat_data["entities"]) == 2

    # 3. Query Mock API entity with pagination
    mock_res = client.get("/api/v1/mock/test_e2e_sch/books?limit=3&offset=0")
    assert mock_res.status_code == 200
    mock_data = mock_res.json()
    assert len(mock_data["data"]) == 3
    assert mock_data["pagination"]["total_records"] == 6

    # 4. Download SQL script
    sql_res = client.get("/api/v1/download/test_e2e_sch/sql")
    assert sql_res.status_code == 200
    assert "CREATE TABLE IF NOT EXISTS" in sql_res.text

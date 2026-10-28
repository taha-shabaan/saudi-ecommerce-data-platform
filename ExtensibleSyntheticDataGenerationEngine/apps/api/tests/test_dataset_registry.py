"""
Tests for the Dataset Registry seam: persisted Generated Datasets that
survive restarts (row store + metadata on disk, one DuckDB file per dataset).
"""

import json
import os
import pytest

from app.core.dataset_registry import DatasetRegistry
from app.core.engine import DataEngine
from app.models.schema import (
    GenerateRequest,
    ConsistencyPolicy,
    AttributeDefinition,
    EntityDefinition,
)


def make_dataset(schema_id="reg_sch", record_count=4):
    request = GenerateRequest(
        schema_id=schema_id,
        name="Registry Test Schema",
        locales=["en_US"],
        entities=[
            EntityDefinition(
                name="users",
                record_count=record_count,
                attributes=[
                    AttributeDefinition(name="id", type="autoincrement", is_primary_key=True),
                    AttributeDefinition(name="name", type="full_name"),
                    AttributeDefinition(
                        name="nickname",
                        type="full_name",
                        nullable=True,
                        null_probability=1.0,
                    ),
                    AttributeDefinition(
                        name="amount",
                        type="numeric_range",
                        params={"min": 10, "max": 90},
                    ),
                ],
            ),
        ],
        policy=ConsistencyPolicy(preset="strict"),
    )
    return request, DataEngine().generate(request)


@pytest.fixture
def registry(tmp_path):
    return DatasetRegistry(base_path=str(tmp_path / "datasets"))


def test_save_persists_rows_metadata_and_round_trips(registry):
    request, dataset = make_dataset()

    meta = registry.save(schema_id="reg_sch", dataset=dataset, request=request)

    assert meta["dataset_id"].startswith("ds_")
    assert meta["schema_id"] == "reg_sch"
    assert meta["row_counts"] == {"users": 4}

    duckdb_path, json_path = registry.paths_for("reg_sch", meta["dataset_id"])
    assert os.path.exists(duckdb_path)
    assert os.path.exists(json_path)

    stored = json.loads(open(json_path).read())
    assert stored["name"] == "Registry Test Schema"
    assert stored["locales"] == ["en_US"]
    assert stored["policy"]["preset"] == "strict"
    assert stored["execution_order"] == ["users"]

    records = registry.load_records("reg_sch", meta["dataset_id"])
    users = records["users"]
    assert len(users) == 4
    assert [u["id"] for u in users] == [1, 2, 3, 4]
    # nullable column survived the round trip as None, not NaN
    assert all(u["nickname"] is None for u in users)
    assert all(isinstance(u["amount"], (int, float)) for u in users)


def test_list_orders_newest_first_and_latest_points_at_newest(registry):
    request, dataset = make_dataset(record_count=4)
    first = registry.save("ord_sch", dataset, request)
    second = registry.save("ord_sch", dataset, request)

    items = registry.list("ord_sch")
    assert len(items) == 2
    assert items[0]["dataset_id"] == second["dataset_id"]
    assert items[1]["dataset_id"] == first["dataset_id"]

    latest = registry.latest("ord_sch")
    assert latest is not None
    assert latest["dataset_id"] == second["dataset_id"]

    assert registry.latest("missing") is None


def test_registry_reads_survive_new_instance_on_same_path(tmp_path):
    base = str(tmp_path / "datasets")
    request, dataset = make_dataset()
    registry = DatasetRegistry(base_path=base)
    meta = registry.save("boot_sch", dataset, request)

    reborn = DatasetRegistry(base_path=base)
    assert len(reborn.list("boot_sch")) == 1
    records = reborn.load_records("boot_sch", meta["dataset_id"])
    assert len(records["users"]) == 4


def test_delete_removes_files_and_reports_unknown(registry):
    request, dataset = make_dataset()
    meta = registry.save("del_sch", dataset, request)
    duckdb_path, json_path = registry.paths_for("del_sch", meta["dataset_id"])

    assert registry.delete("del_sch", meta["dataset_id"]) is True
    assert not os.path.exists(duckdb_path)
    assert not os.path.exists(json_path)
    assert registry.list("del_sch") == []
    assert registry.delete("del_sch", meta["dataset_id"]) is False


def test_rebuild_yields_working_dataset_and_request(registry):
    request, dataset = make_dataset()
    meta = registry.save("rb_sch", dataset, request)

    rebuilt_dataset, rebuilt_request = registry.rebuild("rb_sch", meta["dataset_id"])
    assert rebuilt_dataset.execution_order == ["users"]
    assert len(rebuilt_dataset.records["users"]) == 4
    assert rebuilt_request.schema_id == "rb_sch"
    assert rebuilt_request.name == "Registry Test Schema"
    assert rebuilt_request.entities[0].name == "users"


def test_default_store_path_honours_env(monkeypatch, tmp_path):
    env_dir = str(tmp_path / "env_datasets")
    from app.core import dataset_registry as mod

    monkeypatch.setenv("DATASET_STORE_DIR", env_dir)
    assert mod.default_store_path() == env_dir
    monkeypatch.delenv("DATASET_STORE_DIR")
    assert mod.default_store_path().endswith(os.path.join("data", "api", "datasets")) or \
        mod.default_store_path().endswith("/app/data/datasets")


def test_malicious_dataset_id_is_treated_as_missing(registry):
    with pytest.raises(KeyError):
        registry.paths_for("reg_sch", "..%2F..%2Fsecret")

    with pytest.raises(KeyError):
        registry.get("reg_sch", "../../schema_registry")

    with pytest.raises(KeyError):
        registry.load_records("reg_sch", "x/../../other")

    assert registry.delete("reg_sch", "../schema_registry.db") is False

"""
Persistence for Saved Datasets (see GLOSSARY.md: the sibling of the Schema
Registry). Every generation is saved as a distinct, identifiable version:
entity rows live in one DuckDB file per dataset, generation parameters and
metrics in one JSON sidecar next to it. Both survive process and container
restarts.
"""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import pandas as pd

from app.core.engine import GeneratedDataset
from app.models.schema import GenerateRequest

_store: Optional["DatasetRegistry"] = None


def default_store_path() -> str:
    """Env override, then the container volume path, then ./data/api/datasets."""
    configured = os.environ.get("DATASET_STORE_DIR")
    if configured:
        return configured
    if os.path.isdir("/app"):
        return "/app/data/datasets"
    return os.path.join("data", "api", "datasets")


def _safe_name(value: str) -> str:
    """Reduces a schema_id to a filesystem-safe directory name."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", value).strip()
    return cleaned or "_unnamed"


_DATASET_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class DatasetRegistry:
    """Filesystem store of Saved Datasets, newest-first per schema."""

    def __init__(self, base_path: Optional[str] = None):
        self._base_path = base_path or default_store_path()
        os.makedirs(self._base_path, exist_ok=True)

    def _schema_dir(self, schema_id: str) -> str:
        path = os.path.join(self._base_path, _safe_name(schema_id))
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def _new_dataset_id() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        return f"ds_{stamp}_{uuid.uuid4().hex[:6]}"

    def paths_for(self, schema_id: str, dataset_id: str) -> Tuple[str, str]:
        """The DuckDB row file and JSON metadata path for one dataset."""
        if not _DATASET_ID_PATTERN.match(dataset_id or ""):
            # client-supplied ids must never steer the path outside the store
            raise KeyError(f"Dataset '{dataset_id}' not found for schema '{schema_id}'")
        base = os.path.join(self._base_path, _safe_name(schema_id), dataset_id)
        return f"{base}.duckdb", f"{base}.json"

    def save(
        self,
        schema_id: str,
        dataset: GeneratedDataset,
        request: Optional[GenerateRequest] = None,
    ) -> Dict[str, Any]:
        """Persists rows and metadata as one new dataset version; returns the
        stored metadata dict."""
        dataset_id = self._new_dataset_id()
        duckdb_path, json_path = self.paths_for(schema_id, dataset_id)
        self._schema_dir(schema_id)

        conn = duckdb.connect(duckdb_path)
        try:
            for entity_name in dataset.execution_order:
                records = dataset.records.get(entity_name, [])
                if not records:
                    continue
                df = pd.DataFrame(records)
                conn.register("df_temp", df)
                # quoting guards against reserved words in entity names
                conn.execute(
                    f'CREATE TABLE "{entity_name}" AS SELECT * FROM df_temp'
                )
                conn.unregister("df_temp")
        finally:
            conn.close()

        metadata: Dict[str, Any] = {
            "dataset_id": dataset_id,
            "schema_id": schema_id,
            "name": request.name if request else "Synthetic Dataset",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "row_counts": {k: len(v) for k, v in dataset.records.items()},
            "execution_order": list(dataset.execution_order),
            "metrics": dataset.metrics,
            "warnings": dataset.warnings,
            "locales": request.locales if request else None,
            "policy": request.policy.model_dump() if request else None,
            "request": json.loads(request.model_dump_json()) if request else None,
        }

        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, indent=2)

        return metadata

    def get(self, schema_id: str, dataset_id: str) -> Optional[Dict[str, Any]]:
        """Metadata for one dataset, or None when it does not exist."""
        _, json_path = self.paths_for(schema_id, dataset_id)
        if not os.path.exists(json_path):
            return None
        with open(json_path, encoding="utf-8") as fh:
            return json.load(fh)

    def list(self, schema_id: str) -> List[Dict[str, Any]]:
        """All datasets for a schema, newest first."""
        schema_dir = os.path.join(self._base_path, _safe_name(schema_id))
        items: List[Dict[str, Any]] = []
        if not os.path.isdir(schema_dir):
            return items
        for filename in sorted(os.listdir(schema_dir), reverse=True):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(schema_dir, filename)
            try:
                with open(path, encoding="utf-8") as fh:
                    items.append(json.load(fh))
            except (OSError, json.JSONDecodeError):
                continue  # tolerate partially written or deleted sidecars
        items.sort(key=lambda m: m.get("created_at", ""), reverse=True)
        return items

    def latest(self, schema_id: str) -> Optional[Dict[str, Any]]:
        """The most recent dataset for a schema, or None."""
        items = self.list(schema_id)
        return items[0] if items else None

    def delete(self, schema_id: str, dataset_id: str) -> bool:
        """Removes one dataset version; False when it does not exist."""
        try:
            duckdb_path, json_path = self.paths_for(schema_id, dataset_id)
        except KeyError:
            return False
        if not os.path.exists(json_path) and not os.path.exists(duckdb_path):
            return False
        for path in (duckdb_path, json_path):
            if os.path.exists(path):
                os.remove(path)
        _prune_empty_dir(os.path.dirname(json_path), stop_at=self._base_path)
        return True

    def load_records(self, schema_id: str, dataset_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Rows per entity from the persisted DuckDB file, keyed in the topological
        order recorded at generation time. Python-native fetch keeps None/int/float
        fidelity (pandas DataFrames would turn integer nulls into NaN)."""
        metadata = self.get(schema_id, dataset_id)
        if metadata is None:
            raise KeyError(f"Dataset '{dataset_id}' not found for schema '{schema_id}'")

        duckdb_path, _ = self.paths_for(schema_id, dataset_id)
        conn = duckdb.connect(duckdb_path, read_only=True)
        try:
            tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
            records: Dict[str, List[Dict[str, Any]]] = {}
            entity_names = list(metadata.get("execution_order") or [])
            # tolerate datasets saved before the execution_order sidecar era
            entity_names += sorted(set(tables) - set(entity_names))
            for entity_name in entity_names:
                if entity_name not in tables:
                    continue
                cursor = conn.execute(f'SELECT * FROM "{entity_name}"')
                columns = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                records[entity_name] = [dict(zip(columns, row)) for row in rows]
            return records
        finally:
            conn.close()

    def rebuild(
        self, schema_id: str, dataset_id: str
    ) -> Tuple[GeneratedDataset, Optional[GenerateRequest]]:
        """Reconstructs an in-memory GeneratedDataset plus the original
        GenerateRequest so exporters can re-derive artifacts."""
        metadata = self.get(schema_id, dataset_id)
        if metadata is None:
            raise KeyError(f"Dataset '{dataset_id}' not found for schema '{schema_id}'")

        request: Optional[GenerateRequest] = None
        raw_request = metadata.get("request")
        if raw_request:
            request = GenerateRequest.model_validate(raw_request)
            if request.schema_id != schema_id:
                # rows live under the store key; keep the rebuilt request aligned
                request.schema_id = schema_id

        records = self.load_records(schema_id, dataset_id)
        rebuilt = GeneratedDataset(
            success=True,
            records=records,
            execution_order=list(metadata.get("execution_order") or list(records.keys())),
            metrics=metadata.get("metrics", {}),
            warnings=list(metadata.get("warnings", [])),
        )
        return rebuilt, request

    def open_db(self, schema_id: str, dataset_id: str) -> duckdb.DuckDBPyConnection:
        """A read-only connection to one dataset's DuckDB rows file."""
        duckdb_path, _ = self.paths_for(schema_id, dataset_id)
        if not os.path.exists(duckdb_path):
            raise KeyError(f"Dataset '{dataset_id}' not found for schema '{schema_id}'")
        return duckdb.connect(duckdb_path, read_only=True)


def _prune_empty_dir(path: str, stop_at: str) -> None:
    """Removes now-empty per-schema directories up to (not including) the store root."""
    while path and path != stop_at and os.path.isdir(path):
        if os.listdir(path):
            return
        os.rmdir(path)
        path = os.path.dirname(path)


def get_dataset_registry() -> DatasetRegistry:
    """Process-wide registry instance for the configured store path."""
    global _store
    if _store is None:
        _store = DatasetRegistry()
    return _store


def reset_dataset_registry() -> None:
    """Drops the cached instance so a later call re-reads the configured path."""
    global _store
    _store = None

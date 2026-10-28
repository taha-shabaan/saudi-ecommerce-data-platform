"""
DuckDB-backed serving layer for Saved Datasets and Dynamic Mock REST APIs.

Rows live in one DuckDB file per Saved Dataset (managed by the Dataset
Registry); connections are opened per call (read-only, thread-safe) so
persisted data survives worker restarts without cached connections.
"""

from typing import Any, Dict, List, Optional
import duckdb
import pandas as pd
from app.core.dataset_registry import get_dataset_registry
from app.core.engine import GeneratedDataset
from app.models.schema import GenerateRequest


class DuckDBApiManager:
    """
    Serves Saved Dataset rows through SQL-native pagination and catalog
    lookups, always against the newest dataset for a schema unless a
    dataset_id is given.
    """

    _NOT_FOUND = "not found in mock store"

    @classmethod
    def persist_dataset(
        cls,
        schema_id: str,
        dataset: GeneratedDataset,
        request: Optional[GenerateRequest] = None,
    ) -> Dict[str, Any]:
        """Saves rows and generation parameters as a new dataset version."""
        return get_dataset_registry().save(schema_id, dataset, request)

    @classmethod
    def _resolve(
        cls,
        schema_id: str,
        dataset_id: Optional[str] = None,
    ):
        """Opens a read-only connection to the requested (or latest) dataset."""
        registry = get_dataset_registry()
        metadata = registry.get(schema_id, dataset_id) if dataset_id else registry.latest(schema_id)
        if metadata is None:
            raise KeyError(f"Schema '{schema_id}' {cls._NOT_FOUND}")
        return registry.open_db(schema_id, metadata["dataset_id"]), metadata

    @classmethod
    def query_paginated(
        cls,
        schema_id: str,
        entity_name: str,
        limit: int = 10,
        offset: int = 0,
        dataset_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Queries an entity table with SQL LIMIT and OFFSET."""
        conn, _ = cls._resolve(schema_id, dataset_id)
        try:
            tables = [row[0] for row in conn.execute("SHOW TABLES").fetchall()]
            if entity_name not in tables:
                raise KeyError(
                    f"Entity '{entity_name}' not found for schema '{schema_id}'. Available: {tables}"
                )

            total_records = conn.execute(f'SELECT COUNT(*) FROM "{entity_name}"').fetchone()[0]
            df = conn.execute(
                f'SELECT * FROM "{entity_name}" LIMIT {limit} OFFSET {offset}'
            ).fetch_df()

            records = df.where(pd.notnull(df), None).to_dict(orient="records")
        finally:
            conn.close()

        return {
            "data": records,
            "pagination": {
                "total_records": total_records,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total_records,
            },
        }

    @classmethod
    def get_catalog(cls, schema_id: str, dataset_id: Optional[str] = None) -> Dict[str, Any]:
        """Returns catalog of all entities in the dataset with record counts."""
        conn, metadata = cls._resolve(schema_id, dataset_id)
        try:
            tables = [row[0] for row in conn.execute("SHOW TABLES").fetchall()]
            catalog_entities = []
            for t in tables:
                count = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                catalog_entities.append({"name": t, "record_count": count})
        finally:
            conn.close()

        return {
            "schema_id": schema_id,
            "dataset_id": metadata.get("dataset_id"),
            "entities": catalog_entities,
        }

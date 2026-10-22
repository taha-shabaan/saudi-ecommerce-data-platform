"""
Embedded DuckDB Persistence Manager for Dynamic Mock REST APIs.
"""

from typing import Dict, Any, List, Optional
import duckdb
import pandas as pd
from app.core.engine import GeneratedDataset


class DuckDBApiManager:
    """
    Manages embedded DuckDB analytical database instances per schema ID,
    providing SQL-native pagination and REST endpoint backing.
    """

    _instances: Dict[str, duckdb.DuckDBPyConnection] = {}

    @classmethod
    def get_connection(cls, schema_id: str) -> duckdb.DuckDBPyConnection:
        """Retrieves or initializes an in-memory DuckDB instance for a schema ID."""
        if schema_id not in cls._instances:
            cls._instances[schema_id] = duckdb.connect(database=":memory:")
        return cls._instances[schema_id]

    @classmethod
    def persist_dataset(cls, schema_id: str, dataset: GeneratedDataset):
        """Creates DuckDB tables from generated entity records."""
        conn = cls.get_connection(schema_id)

        for entity_name, records in dataset.records.items():
            if not records:
                continue
            df = pd.DataFrame(records)
            # Register in DuckDB
            conn.register("df_temp", df)
            conn.execute(f'CREATE OR REPLACE TABLE "{entity_name}" AS SELECT * FROM df_temp')
            conn.unregister("df_temp")

    @classmethod
    def query_paginated(
        cls,
        schema_id: str,
        entity_name: str,
        limit: int = 10,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Queries an entity table with SQL LIMIT and OFFSET."""
        conn = cls.get_connection(schema_id)

        # Check if table exists
        tables = [
            row[0] for row in conn.execute("SHOW TABLES").fetchall()
        ]
        if entity_name not in tables:
            raise KeyError(f"Entity '{entity_name}' not found for schema '{schema_id}'. Available: {tables}")

        # Total count
        total_records = conn.execute(f'SELECT COUNT(*) FROM "{entity_name}"').fetchone()[0]

        # Paginated slice
        df = conn.execute(
            f'SELECT * FROM "{entity_name}" LIMIT {limit} OFFSET {offset}'
        ).fetch_df()

        # Handle nulls gracefully for JSON serialization
        records = df.where(pd.notnull(df), None).to_dict(orient="records")

        return {
            "data": records,
            "pagination": {
                "total_records": total_records,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total_records
            }
        }

    @classmethod
    def get_catalog(cls, schema_id: str) -> Dict[str, Any]:
        """Returns catalog of all entities in the schema with record counts."""
        conn = cls.get_connection(schema_id)
        tables = [
            row[0] for row in conn.execute("SHOW TABLES").fetchall()
        ]

        catalog_entities = []
        for t in tables:
            count = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            catalog_entities.append({"name": t, "record_count": count})

        return {
            "schema_id": schema_id,
            "entities": catalog_entities
        }

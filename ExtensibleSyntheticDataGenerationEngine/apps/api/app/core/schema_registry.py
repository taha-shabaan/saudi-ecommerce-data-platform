"""
Persistence for Saved Schemas (see GLOSSARY.md and docs/adr/0001-sqlite-schema-registry.md).

A Saved Schema is a named snapshot of a complete canvas configuration plus the
originating DBML source (when the schema came from a DBDiagram.io import). The
registry is backed by a single SQLite file so schemas survive process and
container restarts.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_DDL = """
CREATE TABLE IF NOT EXISTS saved_schemas (
    name TEXT PRIMARY KEY,
    origin TEXT NOT NULL,
    dbml_source TEXT,
    snapshot TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_registry: Optional["SchemaRegistry"] = None


def default_db_path() -> str:
    """Env override, then the container volume path (ADR-0001), then ./data/api."""
    configured = os.environ.get("SCHEMA_REGISTRY_DB")
    if configured:
        return configured
    if os.path.isdir("/app"):
        return "/app/data/schema_registry.db"
    return os.path.join("data", "api", "schema_registry.db")


class SchemaRegistry:
    """Named store of Saved Schema snapshots on a SQLite file."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        with self._connect() as conn:
            conn.execute(_DDL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def upsert(
        self,
        name: str,
        origin: str,
        dbml_source: Optional[str],
        snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Creates or overwrites the record for `name`. Returns the stored record
        plus a `status` key ('created' or 'updated')."""
        now = self._now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT created_at FROM saved_schemas WHERE name = ?", (name,)
            ).fetchone()
            created_at = row["created_at"] if row else now
            status = "updated" if row else "created"
            conn.execute(
                """
                INSERT INTO saved_schemas (name, origin, dbml_source, snapshot, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    origin = excluded.origin,
                    dbml_source = excluded.dbml_source,
                    snapshot = excluded.snapshot,
                    updated_at = excluded.updated_at
                """,
                (name, origin, dbml_source, json.dumps(snapshot), created_at, now),
            )
        record = self.get(name)  # type: ignore[arg-type]
        record = dict(record)  # type: ignore[arg-type]
        record["status"] = status
        return record

    def list(self) -> List[Dict[str, Any]]:
        """Compact metadata for all saved schemas, most recently updated first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name, origin, snapshot, created_at, updated_at "
                "FROM saved_schemas ORDER BY updated_at DESC"
            ).fetchall()
        items = []
        for row in rows:
            snapshot = json.loads(row["snapshot"])
            items.append({
                "name": row["name"],
                "origin": row["origin"],
                "entity_count": len(snapshot.get("entities", [])),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })
        return items

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        """The full Saved Schema record, or None when the name is unknown."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name, origin, dbml_source, snapshot, created_at, updated_at "
                "FROM saved_schemas WHERE name = ?",
                (name,),
            ).fetchone()
        if row is None:
            return None
        return {
            "name": row["name"],
            "origin": row["origin"],
            "dbml_source": row["dbml_source"],
            "snapshot": json.loads(row["snapshot"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def delete(self, name: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM saved_schemas WHERE name = ?", (name,))
        return cursor.rowcount > 0


def get_registry() -> SchemaRegistry:
    """Process-wide registry instance for the configured database path."""
    global _registry
    if _registry is None:
        _registry = SchemaRegistry(default_db_path())
    return _registry


def reset_cached_registry() -> None:
    """Drops the cached instance so a later call re-reads the configured path."""
    global _registry
    _registry = None

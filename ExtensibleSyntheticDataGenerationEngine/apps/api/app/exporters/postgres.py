"""
PostgreSQL DDL & Batched INSERT Script Exporter.
"""

from typing import List, Dict, Any
from app.models.schema import GenerateRequest, EntityDefinition, AttributeDefinition
from app.core.engine import GeneratedDataset
from app.core.registry import GeneratorRegistry


class PostgresExporter:
    """Generates valid PostgreSQL DDL and chunked INSERT statements."""

    @classmethod
    def generate_ddl_and_dml(
        cls,
        dataset: GeneratedDataset,
        request: GenerateRequest,
        batch_size: int = 500
    ) -> str:
        """
        Produces standalone, executable SQL migration script
        in topological foreign-key order.
        """
        lines: List[str] = [
            "-- ===================================================================",
            "-- SYNTHETIC DATA GENERATION ENGINE: PostgreSQL DDL & DML Migration",
            f"-- Schema: {request.name} (ID: {request.schema_id or 'auto'})",
            f"-- Generated in valid topological foreign-key sequence",
            "-- ===================================================================\n",
            "BEGIN;\n"
        ]

        entity_map: Dict[str, EntityDefinition] = {e.name: e for e in request.entities}

        # 1. DDL Statements (in topological order)
        for entity_name in dataset.execution_order:
            entity = entity_map[entity_name]
            lines.append(f'-- Table: {entity_name}')
            lines.append(f'CREATE TABLE IF NOT EXISTS "{entity_name}" (')
            
            attr_defs: List[str] = []
            for attr in entity.attributes:
                type_str = cls._map_sql_type(attr)
                null_str = "" if attr.nullable else " NOT NULL"
                attr_defs.append(f'    "{attr.name}" {type_str}{null_str}')

            lines.append(",\n".join(attr_defs))
            lines.append(");\n")

        # 2. DML Batched INSERT Statements (in topological order)
        for entity_name in dataset.execution_order:
            records = dataset.records.get(entity_name, [])
            if not records:
                continue

            cols = list(records[0].keys())
            col_list_str = '", "'.join(cols)

            lines.append(f'-- Insert records into: {entity_name} ({len(records)} rows)')

            # Chunk into batches
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                lines.append(f'INSERT INTO "{entity_name}" ("{col_list_str}") VALUES')
                
                row_lines: List[str] = []
                for row in batch:
                    vals = [cls._escape_sql_value(row[col]) for col in cols]
                    row_lines.append(f"    ({', '.join(vals)})")

                lines.append(",\n".join(row_lines) + ";\n")

        lines.append("COMMIT;\n")
        return "\n".join(lines)

    @classmethod
    def _map_sql_type(cls, attr: AttributeDefinition) -> str:
        """Maps an attribute generator type to a PostgreSQL SQL column definition."""
        if attr.type == "autoincrement":
            return "SERIAL PRIMARY KEY" if attr.is_primary_key else "INTEGER"
        elif attr.type == "foreign_key" and attr.fk_target:
            p_entity, p_col = attr.fk_target.split(".")
            pk_clause = " PRIMARY KEY" if attr.is_primary_key else ""
            return f'INTEGER{pk_clause} REFERENCES "{p_entity}"("{p_col}")'
        elif attr.type == "uuid":
            pk_clause = " PRIMARY KEY" if attr.is_primary_key else ""
            return f"UUID{pk_clause}"
        
        meta = GeneratorRegistry.get_meta(attr.type)
        type_str = meta.sql_type if meta else "VARCHAR(255)"
        if attr.is_primary_key:
            type_str += " PRIMARY KEY"
        return type_str

    @classmethod
    def _escape_sql_value(cls, val: Any) -> str:
        """Safely escapes values for SQL literals."""
        if val is None:
            return "NULL"
        if isinstance(val, (int, float)):
            return str(val)
        if isinstance(val, bool):
            return "TRUE" if val else "FALSE"
        clean = str(val).replace("'", "''")
        return f"'{clean}'"

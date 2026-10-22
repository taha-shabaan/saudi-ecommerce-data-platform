"""
Apache Parquet Columnar Exporter using PyArrow.
"""

import io
from typing import Dict, Any, List
import pyarrow as pa
import pyarrow.parquet as pq
from app.core.engine import GeneratedDataset


class ParquetExporter:
    """Exports generated entities into Snappy-compressed Apache Parquet tables."""

    @classmethod
    def export_tables(cls, dataset: GeneratedDataset) -> Dict[str, bytes]:
        """Returns a mapping of entity_name -> parquet byte stream."""
        result: Dict[str, bytes] = {}

        for entity_name in dataset.execution_order:
            records = dataset.records.get(entity_name, [])
            if not records:
                continue

            # Convert to PyArrow Table
            table = pa.Table.from_pylist(records)

            buf = io.BytesIO()
            pq.write_table(table, buf, compression="snappy")
            result[entity_name] = buf.getvalue()

        return result

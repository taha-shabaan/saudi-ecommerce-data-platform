"""
JSON Document Exporter.
"""

import json
from app.core.engine import GeneratedDataset


class JsonDocExporter:
    """Exports dataset records as structured, pretty-printed JSON."""

    @classmethod
    def export_to_json(cls, dataset: GeneratedDataset, indent: int = 2) -> bytes:
        """Serializes all entity records to JSON bytes."""
        json_str = json.dumps(dataset.records, indent=indent, default=str)
        return json_str.encode("utf-8")

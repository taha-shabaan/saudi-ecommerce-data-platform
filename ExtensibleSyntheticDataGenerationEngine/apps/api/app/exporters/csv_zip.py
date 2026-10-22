"""
Zipped CSV Archive Exporter.
"""

import io
import csv
import zipfile
from app.core.engine import GeneratedDataset


class CsvZipExporter:
    """Exports generated entities into individual CSV files inside a .zip archive."""

    @classmethod
    def export_to_zip(cls, dataset: GeneratedDataset) -> bytes:
        """Produces a ZIP archive byte stream containing <entity_name>.csv files."""
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for entity_name in dataset.execution_order:
                records = dataset.records.get(entity_name, [])
                csv_buffer = io.StringIO()
                
                if records:
                    headers = list(records[0].keys())
                    writer = csv.DictWriter(csv_buffer, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(records)
                else:
                    csv_buffer.write("id\n")

                zf.writestr(f"{entity_name}.csv", csv_buffer.getvalue())

        return zip_buffer.getvalue()

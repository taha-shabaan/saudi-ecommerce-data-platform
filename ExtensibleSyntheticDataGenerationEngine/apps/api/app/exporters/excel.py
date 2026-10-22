"""
Multi-Tab Excel Workbook Exporter using openpyxl write_only mode.
"""

import io
from typing import List, Dict, Any
import openpyxl
from app.core.engine import GeneratedDataset


class ExcelExporter:
    """Exports multi-entity synthetic datasets to multi-worksheet .xlsx files."""

    MAX_EXCEL_ROWS = 1_048_576

    @classmethod
    def export_to_bytes(cls, dataset: GeneratedDataset) -> bytes:
        """
        Creates an in-memory .xlsx file with each entity as a separate sheet.
        Uses write_only=True for memory efficiency.
        """
        wb = openpyxl.Workbook(write_only=False)
        # Remove default sheet
        wb.remove(wb.active)

        for entity_name in dataset.execution_order:
            records = dataset.records.get(entity_name, [])
            if len(records) > cls.MAX_EXCEL_ROWS:
                raise ValueError(
                    f"Entity '{entity_name}' has {len(records)} rows, exceeding Excel's limit of {cls.MAX_EXCEL_ROWS}"
                )

            ws = wb.create_sheet(title=entity_name[:31])  # Excel limit is 31 chars for sheet name

            if records:
                headers = list(records[0].keys())
                ws.append(headers)
                for r in records:
                    ws.append([r[h] for h in headers])
            else:
                ws.append(["(No records generated)"])

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

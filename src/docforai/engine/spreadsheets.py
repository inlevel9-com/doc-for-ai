"""Read workbook cells once for both Markdown tables and sheet records."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable, Iterator

from .schema import Converted, markdown_table


def convert_workbook(path: Path, fmt: str) -> Converted:
    if fmt == "xlsx":
        import openpyxl

        engine = f"openpyxl {openpyxl.__version__}"
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
        try:
            # Some exporters write stale dimensions in the worksheet XML.
            for sheet in workbook.worksheets:
                sheet.reset_dimensions()
            sheets, markdown = _render_sheets(
                (sheet.title, sheet.iter_rows(values_only=True)) for sheet in workbook.worksheets
            )
        finally:
            workbook.close()
    else:
        import xlrd

        engine = f"xlrd {xlrd.__version__}"
        with xlrd.open_workbook(str(path), on_demand=True) as workbook:
            sheets, markdown = _render_sheets(
                (sheet.name, _xls_rows(sheet, workbook.datemode)) for sheet in workbook.sheets()
            )
    return Converted(markdown=markdown, engine=engine, sheets=sheets)


def _xls_rows(sheet: Any, datemode: int) -> Iterator[list[Any]]:
    import xlrd

    for row in sheet.get_rows():
        values = []
        for cell in row:
            value = cell.value
            if cell.ctype == xlrd.XL_CELL_DATE:
                date = xlrd.xldate_as_datetime(value, datemode)
                value = date.time() if 0 <= value < 1 else date
            elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                value = bool(value)
            elif cell.ctype == xlrd.XL_CELL_ERROR:
                value = None
            values.append(value)
        yield values


def _cell(value: Any) -> Any:
    if value == "":
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if value.is_integer():
            return int(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _render_sheets(
    worksheets: Iterable[tuple[str, Iterable[Iterable[Any]]]],
) -> tuple[list[dict[str, Any]], str]:
    sheets = []
    sections = []
    for name, values in worksheets:
        rows = []
        for raw_row in values:
            row = [_cell(value) for value in raw_row]
            while row and row[-1] is None:
                row.pop()
            if row:
                rows.append(row)
        if not rows:
            sheets.append({"name": name, "header": [], "records": []})
            sections.append(f"## {name}")
            continue

        header_index = next((i for i, row in enumerate(rows) if sum(v is not None for v in row) >= 2), 0)
        width = max(len(row) for row in rows)
        labels = rows[header_index] + [None] * (width - len(rows[header_index]))
        header = [str(value).strip() if value is not None else f"열{i + 1}" for i, value in enumerate(labels)]

        # Record keys must be unique even when a workbook repeats a header.
        unique_header: list[str] = []
        seen: set[str] = set()
        for label in header:
            key = label
            suffix = 2
            while key in seen:
                key = f"{label}_{suffix}"
                suffix += 1
            unique_header.append(key)
            seen.add(key)
        data_rows = rows[header_index + 1 :]
        records = [dict(zip(unique_header, row + [None] * (width - len(row)))) for row in data_rows]
        sheets.append({"name": name, "header": unique_header, "records": records})
        intro = [" ".join(str(value) for value in row if value is not None) for row in rows[:header_index]]
        sections.append("\n\n".join([f"## {name}", *intro, markdown_table([header, *data_rows])]))
    return sheets, "\n\n".join(sections)

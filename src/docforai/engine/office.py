"""Convert Office documents and PDF using local, format-specific parsers."""

from __future__ import annotations

import zipfile
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Iterator

from .schema import Converted, markdown_table
from .spreadsheets import convert_workbook
from .text_documents import convert_text, html_to_markdown

if TYPE_CHECKING:
    from pptx.shapes.base import BaseShape


def convert_office(path: Path, fmt: str, image_prefix: str) -> Converted:
    if fmt == "docx":
        converted = _convert_docx(path)
    elif fmt == "pptx":
        converted = _convert_pptx(path)
    elif fmt in {"xlsx", "xls"}:
        converted = convert_workbook(path, fmt)
    elif fmt == "pdf":
        converted = _convert_pdf(path)
    else:
        return convert_text(path, fmt)  # 구형 문서 변환 결과가 다른 형식으로 올 때의 안전망

    if fmt in {"docx", "pptx", "xlsx"}:
        converted.images = _ooxml_media(path)
        converted.metadata.update(_ooxml_core_props(path))
        if converted.images:
            links = [f"![{name}]({image_prefix}{name})" for name, _ in converted.images]
            converted.markdown = "\n\n".join([converted.markdown, "\n".join(links)]).strip()
    return converted


def _convert_docx(path: Path) -> Converted:
    import mammoth

    with path.open("rb") as source:
        result = mammoth.convert_to_html(source, convert_image=lambda _: [], external_file_access=False)
    markdown, _ = html_to_markdown(result.value)
    return Converted(markdown, f"mammoth {version('mammoth')}", warnings=[m.message for m in result.messages])


def _reading_order(shapes: Iterable[BaseShape]) -> Iterator[BaseShape]:
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    for shape in sorted(shapes, key=lambda s: (s.top or 0, s.left or 0)):
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _reading_order(shape.shapes)
        else:
            yield shape


def _convert_pptx(path: Path) -> Converted:
    import pptx

    slides = []
    for number, slide in enumerate(pptx.Presentation(str(path)).slides, start=1):
        parts = [f"<!-- Slide number: {number} -->"]
        title = slide.shapes.title
        for shape in _reading_order(slide.shapes):
            if shape.has_table:
                rows = [
                    ["" if cell.is_spanned else cell.text for cell in row.cells]
                    for row in shape.table.rows
                ]
                parts.append(markdown_table(rows))
            elif shape.has_chart:
                parts.extend(_chart_text(shape.chart))
            elif shape.has_text_frame and shape.text.strip():
                prefix = "# " if shape == title else ""
                parts.append(prefix + shape.text.strip().replace("\v", "\n"))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame
            if notes is not None and notes.text.strip():
                parts.extend(["### Notes", notes.text.strip().replace("\v", "\n")])
        slides.append("\n\n".join(parts))
    return Converted("\n\n".join(slides), f"python-pptx {pptx.__version__}")


def _chart_text(chart: Any) -> Iterator[str]:
    if chart.has_title:
        title = chart.chart_title.text_frame.text.strip()
        if title:
            yield title
    for plot in chart.plots:
        series = [(series.name, series.values) for series in plot.series]
        if not series:
            continue
        categories = [category.label for category in getattr(plot, "categories", ())]
        rows = [["Category", *(name for name, _ in series)]]
        for index in range(max(len(values) for _, values in series)):
            label = categories[index] if index < len(categories) else str(index + 1)
            rows.append([label, *(values[index] if index < len(values) else None for _, values in series)])
        yield markdown_table(rows)


def _convert_pdf(path: Path) -> Converted:
    from pdfminer import __version__ as pdfminer_version
    from pdfminer.high_level import extract_text

    pages = extract_text(path).split("\f")
    markdown = "\n\n".join(page.strip() for page in pages if page.strip())

    warnings = []
    if sum(not char.isspace() for char in markdown) < 20:
        warnings.append("글자를 거의 찾지 못했습니다. 스캔(이미지) PDF 이면 OCR 이 필요합니다.")
    return Converted(markdown, f"pdfminer.six {pdfminer_version}", warnings=warnings)


def _ooxml_media(path: Path) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    try:
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                n = info.filename
                if "/media/" in n and not n.endswith("/"):
                    out.append((Path(n).name, z.read(info)))
    except zipfile.BadZipFile:
        pass
    return out


def _ooxml_core_props(path: Path) -> dict[str, Any]:
    try:
        import defusedxml.ElementTree as ET

        with zipfile.ZipFile(path) as z:
            if "docProps/core.xml" not in z.namelist():
                return {}
            root = ET.fromstring(z.read("docProps/core.xml"))
    except Exception:  # noqa: BLE001
        return {}
    ns = {
        "dc": "http://purl.org/dc/elements/1.1/",
        "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
        "dcterms": "http://purl.org/dc/terms/",
    }
    want = {"title": "dc:title", "author": "dc:creator", "subject": "dc:subject", "keywords": "cp:keywords",
            "created": "dcterms:created", "modified": "dcterms:modified"}
    meta = {}
    for k, tag in want.items():
        el = root.find(tag, ns)
        if el is not None and (el.text or "").strip():
            meta[k] = el.text.strip()
    return meta

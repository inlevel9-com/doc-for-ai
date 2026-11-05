"""Convert local text, Markdown, HTML, CSV, JSON, XML, and EPUB files."""

from __future__ import annotations

import codecs
import csv
import io
import json
import posixpath
from importlib.metadata import version
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

from .schema import Converted, code_fence, markdown_table

STDLIB = "Python standard library"


def _decode(data: bytes) -> str:
    if data.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        return data.decode("utf-32")
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        from charset_normalizer import from_bytes

        match = from_bytes(data).best()
        return str(match) if match else data.decode("utf-8", errors="replace")


def html_to_markdown(html: str | bytes) -> tuple[str, str | None]:
    from bs4 import BeautifulSoup
    from markdownify import MarkdownConverter

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    for tag in soup.find_all(["script", "style", "head", "template", "noscript"]):
        tag.decompose()

    converter = MarkdownConverter(heading_style="ATX", table_infer_header=True)
    markdown = converter.convert_soup(soup.body or soup)
    return markdown.strip(), title


def _convert_epub(path: Path) -> Converted:
    from defusedxml.ElementTree import fromstring

    with ZipFile(path) as archive:
        container = fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find(".//{*}rootfile")
        if rootfile is None or not rootfile.get("full-path"):
            raise ValueError("EPUB package document is missing")
        package_path = rootfile.attrib["full-path"]
        package = fromstring(archive.read(package_path))
        title = package.findtext(".//{*}metadata/{*}title")
        authors = [creator.text for creator in package.findall(".//{*}metadata/{*}creator") if creator.text]
        manifest = {
            item.get("id"): item.get("href", "")
            for item in package.findall(".//{*}manifest/{*}item")
        }
        chapters = []
        warnings = []
        entries = set(archive.namelist())
        parent = posixpath.dirname(package_path)
        for item in package.findall(".//{*}spine/{*}itemref"):
            href = urlsplit(manifest.get(item.get("idref"), ""))
            if href.scheme or href.netloc or not href.path:
                warnings.append("EPUB chapter has no local archive entry.")
                continue
            for name in (unquote(href.path), href.path):
                chapter = posixpath.normpath(posixpath.join(parent, name))
                if chapter in entries:
                    markdown, _ = html_to_markdown(archive.read(chapter))
                    chapters.append(markdown)
                    break
            else:
                warnings.append(f"EPUB chapter is missing: {href.path}")

    metadata = {}
    if title:
        metadata["title"] = title
    if authors:
        metadata["author"] = ", ".join(authors)
    return Converted("\n\n".join(chapters), f"markdownify {version('markdownify')}", metadata=metadata, warnings=warnings)


# ---------- JSON ----------

def _is_flat_record(value: Any) -> bool:
    return isinstance(value, dict) and all(not isinstance(v, (dict, list)) for v in value.values())


def _records_table(records: list[dict[str, Any]]) -> tuple[list[str], list[list[Any]]]:
    header: list[str] = []
    for record in records:
        for key in record:
            if str(key) not in header:
                header.append(str(key))
    rows = [[record.get(key) for key in header] for record in records]
    return header, rows


def _convert_json(text: str) -> Converted:
    try:
        data = json.loads(text)
    except ValueError as e:
        return Converted(code_fence(text, "json"), STDLIB,
                         warnings=[f"JSON 문법 오류가 있어 원문 그대로 실었습니다: {str(e)[:120]}"])

    # 같은 모양의 객체 목록(레코드)이면 표로, 아니면 보기 좋게 정리한 원문으로
    records = None
    name = "data"
    if isinstance(data, list) and data and all(_is_flat_record(x) for x in data):
        records = data
    elif isinstance(data, dict) and len(data) == 1:
        key, value = next(iter(data.items()))
        if isinstance(value, list) and value and all(_is_flat_record(x) for x in value):
            records, name = value, str(key)
    if records is not None:
        header, rows = _records_table(records)
        sheets = [{"name": name, "header": header, "records": [dict(zip(header, row)) for row in rows]}]
        return Converted(markdown_table([header, *rows]), STDLIB, sheets=sheets)

    pretty = json.dumps(data, ensure_ascii=False, indent=2)
    return Converted(code_fence(pretty, "json"), STDLIB)


# ---------- XML ----------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _feed_to_markdown(root: Any) -> str | None:
    """RSS 2.0 / Atom 피드는 글 목록으로 풀어 쓴다. 피드가 아니면 None."""
    kind = _local(root.tag).lower()
    if kind == "rss":
        channel = root.find("{*}channel")
        if channel is None:
            return None
        items, title_tag, body_tags, date_tag = channel.findall("{*}item"), "title", ("description", "encoded"), "pubDate"
        feed_title = channel.findtext("{*}title")
    elif kind == "feed":
        items, title_tag, body_tags, date_tag = root.findall("{*}entry"), "title", ("content", "summary"), "updated"
        feed_title = root.findtext("{*}title")
    else:
        return None

    parts = [f"# {feed_title.strip()}"] if feed_title and feed_title.strip() else []
    for item in items:
        title = (item.findtext(f"{{*}}{title_tag}") or "").strip()
        parts.append(f"## {title}" if title else "## (제목 없음)")
        date = (item.findtext(f"{{*}}{date_tag}") or "").strip()
        if date:
            parts.append(f"날짜: {date}")
        for tag in body_tags:
            body = item.findtext(f"{{*}}{tag}")
            if body and body.strip():
                markdown, _ = html_to_markdown(body)
                if markdown:
                    parts.append(markdown)
                break
    return "\n\n".join(parts)


def _convert_xml(text: str) -> Converted:
    import xml.etree.ElementTree as ET

    from defusedxml import DefusedXmlException
    from defusedxml.ElementTree import fromstring

    try:
        root = fromstring(text.encode("utf-8"))
    except ET.ParseError as e:
        return Converted(code_fence(text, "xml"), STDLIB,
                         warnings=[f"XML 문법 오류가 있어 원문 그대로 실었습니다: {str(e)[:120]}"])
    except DefusedXmlException:
        return Converted(code_fence(text, "xml"), STDLIB,
                         warnings=["엔티티·DTD 가 있는 XML 은 안전을 위해 해석하지 않고 원문 그대로 실었습니다."])

    feed = _feed_to_markdown(root)
    if feed is not None:
        return Converted(feed, STDLIB, metadata={"format_version": "rss/atom"})

    ET.indent(root)
    pretty = ET.tostring(root, encoding="unicode")
    return Converted(code_fence(pretty, "xml"), STDLIB)


def convert_text(path: Path, fmt: str) -> Converted:
    if fmt == "epub":
        return _convert_epub(path)
    data = path.read_bytes()
    if fmt in {"html", "htm"}:
        markdown, title = html_to_markdown(data)
        return Converted(markdown, f"markdownify {version('markdownify')}", metadata={"title": title} if title else {})
    text = _decode(data)
    if fmt == "csv":
        rows = [row for row in csv.reader(io.StringIO(text, newline="")) if row]
        text = markdown_table(rows)
    elif fmt == "json":
        return _convert_json(text)
    elif fmt == "xml":
        return _convert_xml(text)
    return Converted(text, STDLIB)

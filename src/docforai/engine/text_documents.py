"""Convert local text, HTML, CSV, and EPUB files."""

from __future__ import annotations

import codecs
import csv
import io
import posixpath
from importlib.metadata import version
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

from .schema import Converted, markdown_table


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
    return Converted(text, "Python standard library")

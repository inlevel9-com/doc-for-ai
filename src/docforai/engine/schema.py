"""AI 학습용 정규화 JSON 문서 모델.

어떤 원본 형식이든 같은 구조로 내보낸다:
  document = { schema, source, metadata, markdown, blocks, tables, sheets, chunks, warnings }

blocks 는 Markdown 을 줄 단위로 해석해 만든다. 완벽한 Markdown 파서가 아니라
변환기가 내보내는 Markdown(제목·문단·표·목록·이미지·슬라이드 구분)만 다룬다.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_ID = "docforai/1.0"

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_ULIST = re.compile(r"^\s*[-*+]\s+(.*)$")
_OLIST = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
_IMAGE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
_SLIDE = re.compile(r"^<!--\s*Slide number:\s*(\d+)\s*-->\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


@dataclass
class Converted:
    """개별 변환기(hwp/office)가 돌려주는 중간 결과."""

    markdown: str
    engine: str
    metadata: dict[str, Any] = field(default_factory=dict)
    images: list[tuple[str, bytes]] = field(default_factory=list)  # (파일명, 바이트)
    sheets: list[dict[str, Any]] | None = None  # 엑셀 전용: [{name, header, records}]
    warnings: list[str] = field(default_factory=list)


def markdown_table(rows: list[list[Any]]) -> str:
    width = max((len(row) for row in rows), default=0)
    if not width:
        return ""

    def render_row(row: list[Any]) -> str:
        values = ["" if cell is None else " ".join(str(cell).splitlines()).replace("|", r"\|") for cell in row]
        values.extend([""] * (width - len(values)))
        return "| " + " | ".join(values) + " |"

    return "\n".join([render_row(rows[0]), render_row(["---"] * width), *(render_row(row) for row in rows[1:])])


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    # 이스케이프된 파이프(\|)는 셀 안의 문자로 유지
    cells = re.split(r"(?<!\\)\|", s)
    return [c.replace("\\|", "|").strip() for c in cells]


def markdown_to_blocks(md: str) -> list[dict[str, Any]]:
    lines = md.splitlines()
    blocks: list[dict[str, Any]] = []
    para: list[str] = []
    i = 0

    def flush_para() -> None:
        if para:
            text = "\n".join(para).strip()
            if text:
                blocks.append({"type": "paragraph", "text": text})
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            flush_para()
            i += 1
            continue

        m = _SLIDE.match(stripped)
        if m:
            flush_para()
            blocks.append({"type": "slide", "number": int(m.group(1))})
            i += 1
            continue

        m = _HEADING.match(stripped)
        if m:
            flush_para()
            blocks.append({"type": "heading", "level": len(m.group(1)), "text": m.group(2)})
            i += 1
            continue

        m = _IMAGE.match(stripped)
        if m:
            flush_para()
            blocks.append({"type": "image", "alt": m.group(1), "path": m.group(2)})
            i += 1
            continue

        # 표: 첫 줄이 |로 시작하고 다음 줄이 구분선이면 표로 본다
        if "|" in stripped and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]):
            flush_para()
            header = _split_row(stripped)
            rows: list[list[str]] = []
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(_split_row(lines[i]))
                i += 1
            blocks.append({"type": "table", "header": header, "rows": rows})
            continue

        m = _ULIST.match(line) or _OLIST.match(line)
        if m:
            flush_para()
            ordered = bool(_OLIST.match(line))
            items: list[str] = []
            while i < len(lines):
                mm = _OLIST.match(lines[i]) if ordered else _ULIST.match(lines[i])
                if not mm:
                    break
                items.append(mm.group(2) if ordered else mm.group(1))
                i += 1
            blocks.append({"type": "list", "ordered": ordered, "items": items})
            continue

        para.append(stripped)
        i += 1

    flush_para()
    return blocks


def _table_as_text(block: dict[str, Any]) -> str:
    parts = [" | ".join(block["header"])]
    parts += [" | ".join(r) for r in block["rows"]]
    return "\n".join(parts)


def _block_text(block: dict[str, Any]) -> str:
    t = block["type"]
    if t in ("paragraph", "heading"):
        return block["text"]
    if t == "list":
        return "\n".join(f"- {x}" for x in block["items"])
    if t == "table":
        return _table_as_text(block)
    if t == "image":
        return f"[이미지: {block.get('alt') or block['path']}]"
    return ""


def build_chunks(blocks: list[dict[str, Any]], max_chars: int = 1500) -> list[dict[str, Any]]:
    """제목 경로 기준으로 묶은 뒤 너무 길면 문단 단위로 나눈다. RAG·파인튜닝 입력용."""
    chunks: list[dict[str, Any]] = []
    path: list[str] = []
    buf: list[str] = []
    buf_path: list[str] = []

    def flush() -> None:
        text = "\n\n".join(buf).strip()
        if text:
            chunks.append({"id": len(chunks) + 1, "heading_path": list(buf_path), "text": text})
        buf.clear()

    for b in blocks:
        if b["type"] == "heading":
            flush()
            lvl = b["level"]
            path = path[: lvl - 1] + [b["text"]]
            buf_path = list(path)
            continue
        if b["type"] == "slide":
            flush()
            buf_path = list(path) + [f"슬라이드 {b['number']}"]
            continue
        text = _block_text(b)
        if not text:
            continue
        if buf and sum(len(x) for x in buf) + len(text) > max_chars:
            flush()
            buf_path = list(path) if not buf_path else buf_path
        if len(text) > max_chars:
            flush()
            for k in range(0, len(text), max_chars):
                buf.append(text[k : k + max_chars])
                flush()
            continue
        buf.append(text)
    flush()
    return chunks


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_document(source: Path, conv: Converted, fmt: str) -> dict[str, Any]:
    blocks = markdown_to_blocks(conv.markdown)
    tables = [b for b in blocks if b["type"] == "table"]
    stat = source.stat()
    doc: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "source": {
            "file_name": source.name,
            "format": fmt,
            "size_bytes": stat.st_size,
            "sha256": sha256_of(source),
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "converted_at": datetime.now(tz=timezone.utc).isoformat(),
            "engine": conv.engine,
        },
        "metadata": conv.metadata,
        "markdown": conv.markdown,
        "blocks": blocks,
        "tables": tables,
        "chunks": build_chunks(blocks),
        "warnings": conv.warnings,
    }
    if conv.sheets is not None:
        doc["sheets"] = conv.sheets
    return doc

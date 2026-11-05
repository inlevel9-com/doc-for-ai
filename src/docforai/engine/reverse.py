"""Turn a docforai JSON document back into an Excel workbook.

매핑 규칙은 docs/JSON_SCHEMA.md 의 'JSON → Excel' 절에 적혀 있다. 요약:
  - '정보' 시트: 출처·메타데이터 키/값
  - sheets 가 있으면(엑셀·표 형태 JSON 원본) 시트를 그대로 복원하고 끝
  - 아니면 '본문' 시트에 블록을 순서대로 한 줄씩, 표 블록은 '표1', '표2'… 시트로
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .schema import SCHEMA_ID

_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_SHEET_BAD = re.compile(r"[\[\]:*?/\\]")
MAX_CELL = 32767  # 엑셀 셀 글자 수 한계
BODY_HEADER = ["순번", "종류", "수준·번호", "내용"]


class NotDocforaiJson(ValueError):
    pass


def load_document(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        raise NotDocforaiJson(f"JSON 을 읽을 수 없습니다: {str(e)[:120]}") from e
    if not isinstance(doc, dict) or not str(doc.get("schema", "")).startswith("docforai/"):
        raise NotDocforaiJson("이 프로그램이 만든 JSON(docforai/1.0)이 아닙니다. 변환결과 폴더의 .json 파일을 고르세요.")
    return doc


def _cell(value: Any, warnings: list[str]) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    value = _ILLEGAL.sub("", value)
    if len(value) > MAX_CELL:
        warnings.append(f"셀 하나가 {MAX_CELL:,}자를 넘어 잘랐습니다.")
        value = value[:MAX_CELL]
    return value


def _write_rows(ws: Any, rows: list[list[Any]], warnings: list[str]) -> None:
    for row in rows:
        ws.append([_cell(v, warnings) for v in row])
        # '=' 로 시작하는 글은 수식이 아니라 글자로 남긴다
        for cell in ws[ws.max_row]:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                cell.data_type = "s"
    _style(ws, len(rows[0]) if rows else 0)


def _style(ws: Any, width: int) -> None:
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    if ws.max_row < 1 or width == 0:
        return
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"
    for col in range(1, width + 1):
        longest = max((len(str(c.value)) for c in ws[get_column_letter(col)] if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(col)].width = min(max(10, longest + 2), 60)


def _sheet_name(title: str, used: set[str]) -> str:
    base = _SHEET_BAD.sub("_", str(title)).strip() or "Sheet"
    base = base[:28]
    name, n = base, 2
    while name.lower() in used:
        name = f"{base[:28 - len(str(n)) - 1]}_{n}"
        n += 1
    used.add(name.lower())
    return name


def _info_rows(doc: dict[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = [["항목", "값"]]
    rows.append(["schema", doc.get("schema", SCHEMA_ID)])
    for key, value in (doc.get("source") or {}).items():
        rows.append([f"source.{key}", value])
    for key, value in (doc.get("metadata") or {}).items():
        rows.append([f"metadata.{key}", value])
    for w in doc.get("warnings") or []:
        rows.append(["warning", w])
    return rows


def _body_rows(blocks: list[dict[str, Any]]) -> tuple[list[list[Any]], list[tuple[str, dict[str, Any]]]]:
    rows: list[list[Any]] = [BODY_HEADER]
    tables: list[tuple[str, dict[str, Any]]] = []
    n = 0

    def add(kind: str, level: Any, text: Any) -> None:
        nonlocal n
        n += 1
        rows.append([n, kind, level, text])

    for b in blocks:
        t = b.get("type")
        if t == "heading":
            add("제목", b.get("level"), b.get("text", ""))
        elif t == "paragraph":
            add("문단", None, b.get("text", ""))
        elif t == "list":
            kind = "번호목록" if b.get("ordered") else "글머리목록"
            for i, item in enumerate(b.get("items") or [], 1):
                add(kind, i, item)
        elif t == "table":
            name = f"표{len(tables) + 1}"
            tables.append((name, b))
            add("표", name, f"{len(b.get('rows') or [])}행 × {len(b.get('header') or [])}열 → 시트 '{name}'")
        elif t == "image":
            alt, path = b.get("alt") or "", b.get("path") or ""
            add("그림", None, f"{alt}: {path}" if alt and alt != path else path)
        elif t == "slide":
            add("슬라이드", b.get("number"), None)
        elif t == "code":
            add("코드", b.get("language") or None, b.get("text", ""))
        else:
            add(str(t), None, json.dumps(b, ensure_ascii=False))
    return rows, tables


def document_to_workbook(doc: dict[str, Any]) -> tuple[Any, list[str]]:
    from openpyxl import Workbook

    warnings: list[str] = []
    wb = Workbook()
    used: set[str] = set()
    info = wb.active
    info.title = _sheet_name("정보", used)
    _write_rows(info, _info_rows(doc), warnings)

    sheets = doc.get("sheets")
    if sheets:
        for sheet in sheets:
            ws = wb.create_sheet(_sheet_name(sheet.get("name") or "Sheet", used))
            header = [str(h) for h in sheet.get("header") or []]
            records = sheet.get("records") or []
            if not header and records:
                header = [str(k) for k in records[0]]
            rows = [header] + [[r.get(h) for h in header] for r in records] if header else []
            _write_rows(ws, rows, warnings)
        return wb, warnings

    body_rows, tables = _body_rows(doc.get("blocks") or [])
    body = wb.create_sheet(_sheet_name("본문", used))
    _write_rows(body, body_rows, warnings)
    for name, block in tables:
        ws = wb.create_sheet(_sheet_name(name, used))
        header = [str(h) for h in block.get("header") or []]
        width = max([len(header), *(len(r) for r in block.get("rows") or [])], default=0)
        rows = [header + [""] * (width - len(header))] + [list(r) + [""] * (width - len(r)) for r in block.get("rows") or []]
        _write_rows(ws, rows, warnings)
    return wb, warnings


def json_to_xlsx(source: Path, out_dir: Path | None = None) -> tuple[Path, list[str]]:
    """docforai JSON → 같은 이름의 .xlsx. 기본 저장 위치는 JSON 파일 옆."""
    source = Path(source)
    doc = load_document(source)
    wb, warnings = document_to_workbook(doc)
    target_dir = Path(out_dir) if out_dir else source.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{source.stem}.xlsx"
    wb.save(target)
    return target, warnings

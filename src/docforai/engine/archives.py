"""Convert every supported document inside a ZIP archive into one combined result.

압축 파일 하나 → 결과 하나. 안의 문서는 각각 변환한 뒤 '# 경로' 제목 아래 차례로 잇는다.
"""
from __future__ import annotations

import posixpath
import re
import zipfile
from pathlib import Path
from typing import Any, Callable

from .schema import Converted

MAX_DEPTH = 2  # 압축 안의 압축까지만
MAX_ENTRY_BYTES = 512 * 1024 * 1024
_HEADING = re.compile(r"^(#{1,5})(\s)", re.MULTILINE)
_UNSAFE = re.compile(r"[^\w.\-가-힣 ]+")

Convert = Callable[[Path, str, str, Path], Converted]


def _safe_stem(name: str) -> str:
    return _UNSAFE.sub("_", Path(name).stem).strip("_ ") or "entry"


def convert_archive(path: Path, image_prefix: str, workdir: Path, convert: Convert,
                    supported: set[str], depth: int = 0) -> Converted:
    from . import friendly_error

    sections: list[str] = []
    images: list[tuple[str, bytes]] = []
    image_names: set[str] = set()
    sheets: list[dict[str, Any]] = []
    warnings: list[str] = []
    entries: list[str] = []
    extract_dir = workdir / f"zip{depth}_{_safe_stem(path.name)}"
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(path) as archive:
        infos = sorted((i for i in archive.infolist() if not i.is_dir()), key=lambda i: i.filename)
        for index, info in enumerate(infos):
            name = info.filename
            base = posixpath.basename(name)
            if name.startswith("__MACOSX/") or base.startswith((".", "~$")):
                continue
            fmt = base.rsplit(".", 1)[-1].lower() if "." in base else ""
            if fmt == "zip" and depth >= MAX_DEPTH:
                warnings.append(f"{name}: 압축이 너무 깊어 건너뜀")
                continue
            if fmt not in supported:
                warnings.append(f"{name}: 지원하지 않는 형식이라 건너뜀")
                continue
            if info.file_size > MAX_ENTRY_BYTES:
                warnings.append(f"{name}: 너무 커서 건너뜀")
                continue
            target = extract_dir / f"{index:04d}" / (_UNSAFE.sub("_", base) or f"entry.{fmt}")
            target.parent.mkdir(exist_ok=True)
            with archive.open(info) as src, target.open("wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
            try:
                if fmt == "zip":
                    conv = convert_archive(target, image_prefix, workdir, convert, supported, depth + 1)
                else:
                    conv = convert(target, fmt, image_prefix, workdir)
            except Exception as e:  # noqa: BLE001 - 한 파일이 실패해도 나머지는 계속
                warnings.append(f"{name}: {friendly_error(e)}")
                continue

            stem = _safe_stem(base)
            markdown = _HEADING.sub(r"#\1\2", conv.markdown)  # 제목을 한 단계 내려 파일 제목 아래에 둔다
            for img_name, data in conv.images:
                new_name = img_name if img_name == target.name else f"{stem}_{img_name}"
                while new_name in image_names:
                    new_name = f"{index:04d}_{new_name}"
                image_names.add(new_name)
                markdown = markdown.replace(f"({image_prefix}{img_name})", f"({image_prefix}{new_name})")
                images.append((new_name, data))
            for sheet in conv.sheets or []:
                sheets.append({**sheet, "name": f"{stem}/{sheet['name']}"})
            warnings.extend(f"{name}: {w}" for w in conv.warnings)
            entries.append(name)
            sections.append(f"# {name}\n\n{markdown.strip()}".rstrip())

    if not entries:
        warnings.append("압축 파일 안에서 변환할 수 있는 문서를 찾지 못했습니다.")
    return Converted("\n\n".join(sections), "zipfile (Python standard library)",
                     metadata={"entries": entries}, images=images,
                     sheets=sheets or None, warnings=warnings)

"""변환 엔진 진입점.

    from docforai.engine import convert_file, ConvertOptions
    result = convert_file(Path("보고서.hwp"), ConvertOptions())

형식 판별 → 전용 변환기 → 정규화 JSON → 파일 쓰기. GUI/CLI 는 이 모듈만 호출한다.
외부 네트워크는 어디서도 쓰지 않는다.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import traceback
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .media import AUDIO_FORMATS, IMAGE_FORMATS
from .schema import Converted, build_document

OUTPUT_DIR_NAME = "변환결과"

HWP_FORMATS = {"hwp", "hwpx", "hwt", "hml"}
OFFICE_FORMATS = {"docx", "pptx", "xlsx", "xls", "pdf"}
TEXT_FORMATS = {"csv", "html", "htm", "txt", "md", "markdown", "json", "xml", "epub"}
ARCHIVE_FORMATS = {"zip"}
LEGACY_FORMATS = {"doc", "ppt", "rtf", "odt", "odp", "ods"}
SUPPORTED = HWP_FORMATS | OFFICE_FORMATS | TEXT_FORMATS | ARCHIVE_FORMATS | IMAGE_FORMATS | AUDIO_FORMATS | LEGACY_FORMATS

FORMAT_LABEL = {
    "hwp": "한글 문서", "hwpx": "한글 문서(HWPX)", "hwt": "한글 서식", "hml": "한글 HML",
    "docx": "워드", "doc": "워드(구형)", "pptx": "파워포인트", "ppt": "파워포인트(구형)",
    "xlsx": "엑셀", "xls": "엑셀(구형)", "pdf": "PDF", "csv": "CSV", "txt": "텍스트",
    "md": "Markdown", "markdown": "Markdown", "html": "웹 문서", "htm": "웹 문서", "json": "JSON", "xml": "XML",
    "epub": "전자책", "zip": "압축 파일", "rtf": "서식 있는 텍스트",
    "odt": "오픈문서 글", "odp": "오픈문서 발표", "ods": "오픈문서 표",
    **{e: "그림" for e in IMAGE_FORMATS}, **{e: "소리" for e in AUDIO_FORMATS},
}


@dataclass
class ConvertOptions:
    write_markdown: bool = True
    write_json: bool = True
    save_images: bool = True
    out_dir: Path | None = None  # None 이면 원본 옆 '변환결과' 폴더
    overwrite: bool = True


@dataclass
class ConvertResult:
    source: Path
    ok: bool
    message: str
    outputs: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fmt: str = ""


def detect_format(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if ext == "hwpx" or ext == "hwp":
        # 확장자가 틀린 경우 대비: HWPX 는 ZIP, HWP 5 는 OLE, HWP 3 는 'HWP Document File'
        try:
            with path.open("rb") as f:
                head = f.read(8)
            if head.startswith(b"PK"):
                return "hwpx"
            if head.startswith(b"\xd0\xcf\x11\xe0"):
                return "hwp"
        except OSError:
            pass
    return ext


def iter_documents(paths: Iterable[Path]) -> list[Path]:
    """파일/폴더 목록을 받아 지원하는 문서 파일 목록으로 펼친다(폴더는 하위까지)."""
    out: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and not f.name.startswith(("~$", ".")) and OUTPUT_DIR_NAME not in f.parts:
                    if f.suffix.lower().lstrip(".") in SUPPORTED:
                        out.append(f)
        elif p.is_file():
            out.append(p)
    # 중복 제거(순서 유지)
    seen: set[Path] = set()
    uniq = []
    for f in out:
        r = f.resolve()
        if r not in seen:
            seen.add(r)
            uniq.append(f)
    return uniq


def _output_dir(source: Path, opts: ConvertOptions) -> Path:
    base = opts.out_dir if opts.out_dir else source.parent / OUTPUT_DIR_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def _convert(source: Path, fmt: str, image_prefix: str, workdir: Path) -> Converted:
    if fmt in HWP_FORMATS:
        from .hwp import convert_hwp

        return convert_hwp(source, image_prefix)
    if fmt in LEGACY_FORMATS:
        from .legacy import convert_legacy
        from .office import convert_office

        modern = convert_legacy(source, fmt, workdir)
        conv = convert_office(modern, modern.suffix.lstrip("."), image_prefix)
        conv.engine += " + LibreOffice"
        return conv
    if fmt in OFFICE_FORMATS:
        from .office import convert_office

        return convert_office(source, fmt, image_prefix)
    if fmt in TEXT_FORMATS:
        from .text_documents import convert_text

        return convert_text(source, "md" if fmt == "markdown" else fmt)
    if fmt in IMAGE_FORMATS:
        from .media import convert_image

        return convert_image(source, image_prefix)
    if fmt in AUDIO_FORMATS:
        from .media import convert_audio

        return convert_audio(source)
    if fmt in ARCHIVE_FORMATS:
        from .archives import convert_archive

        return convert_archive(source, image_prefix, workdir, _convert, SUPPORTED)
    raise ValueError(f"지원하지 않는 형식입니다: .{fmt}")


def convert_file(source: Path, opts: ConvertOptions | None = None) -> ConvertResult:
    opts = opts or ConvertOptions()
    source = Path(source)
    fmt = detect_format(source)
    if fmt not in SUPPORTED:
        return ConvertResult(source, False, f"지원하지 않는 파일 형식입니다 (.{fmt})", fmt=fmt)
    if not source.exists():
        return ConvertResult(source, False, "파일을 찾을 수 없습니다", fmt=fmt)

    workdir = Path(tempfile.mkdtemp(prefix="docforai_"))
    try:
        out_dir = _output_dir(source, opts)
        stem = source.stem
        assets_name = f"{stem}_files"
        conv = _convert(source, fmt, f"{assets_name}/", workdir)
        doc = build_document(source, conv, fmt)

        outputs: list[Path] = []
        if opts.write_markdown:
            md_path = out_dir / f"{stem}.md"
            md_path.write_text(_with_frontmatter(doc), encoding="utf-8")
            outputs.append(md_path)
        if opts.write_json:
            js_path = out_dir / f"{stem}.json"
            js_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
            outputs.append(js_path)
        if opts.save_images and conv.images:
            adir = out_dir / assets_name
            adir.mkdir(exist_ok=True)
            for name, data in conv.images:
                (adir / Path(name).name).write_bytes(data)
            outputs.append(adir)

        n_chars = len(conv.markdown)
        msg = f"완료 · 글자 {n_chars:,}자"
        if conv.images:
            msg += f" · 그림 {len(conv.images)}장"
        if conv.sheets:
            msg += f" · 시트 {len(conv.sheets)}개"
        if fmt in ARCHIVE_FORMATS:
            msg += f" · 문서 {len(conv.metadata.get('entries') or [])}개"
        return ConvertResult(source, True, msg, outputs, list(conv.warnings), fmt)
    except Exception as e:  # noqa: BLE001 - 사용자에게는 원인만 짧게, 로그에는 전체
        return ConvertResult(source, False, friendly_error(e), warnings=[traceback.format_exc()], fmt=fmt)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def convert_many(paths: Iterable[Path], opts: ConvertOptions | None = None,
                 progress: Callable[[int, int, ConvertResult], None] | None = None) -> list[ConvertResult]:
    files = iter_documents(paths)
    results = []
    for i, f in enumerate(files, 1):
        r = convert_file(f, opts)
        results.append(r)
        if progress:
            progress(i, len(files), r)
    return results


def excel_from_json(source: Path, opts: ConvertOptions | None = None) -> ConvertResult:
    """역변환: 이 프로그램이 만든 JSON → 엑셀(.xlsx). GUI/CLI 양쪽에서 쓴다."""
    from .reverse import NotDocforaiJson, json_to_xlsx

    opts = opts or ConvertOptions()
    source = Path(source)
    if not source.exists():
        return ConvertResult(source, False, "파일을 찾을 수 없습니다", fmt="json")
    try:
        target, warnings = json_to_xlsx(source, opts.out_dir)
    except NotDocforaiJson as e:
        return ConvertResult(source, False, str(e), fmt="json")
    except Exception as e:  # noqa: BLE001
        return ConvertResult(source, False, friendly_error(e), warnings=[traceback.format_exc()], fmt="json")
    return ConvertResult(source, True, f"완료 · {target.name}", [target], warnings, "json")


def excel_from_json_many(paths: Iterable[Path], opts: ConvertOptions | None = None,
                         progress: Callable[[int, int, ConvertResult], None] | None = None) -> list[ConvertResult]:
    files: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            files.extend(f for f in sorted(p.rglob("*.json")) if f.is_file() and not f.name.startswith("."))
        else:
            files.append(p)
    results = []
    for i, f in enumerate(files, 1):
        r = excel_from_json(f, opts)
        results.append(r)
        if progress:
            progress(i, len(files), r)
    return results


def friendly_error(e: Exception) -> str:
    from .hwp import HwpLocked
    from .legacy import LegacyPackMissing

    if isinstance(e, (HwpLocked,)):
        return "암호가 걸려 있거나 배포용 문서라 내용을 읽을 수 없습니다"
    if isinstance(e, LegacyPackMissing):
        return str(e)
    if isinstance(e, zipfile.BadZipFile):
        return "압축 파일이 손상되었거나 ZIP 형식이 아닙니다"
    if isinstance(e, PermissionError):
        return "파일이 다른 프로그램에서 열려 있거나 권한이 없습니다"
    if isinstance(e, MemoryError):
        return "파일이 너무 커서 메모리가 부족합니다"
    text = str(e) or type(e).__name__
    if "password" in text.lower() or "encrypt" in text.lower():
        return "암호가 걸린 문서라 내용을 읽을 수 없습니다"
    return f"변환 실패: {text[:160]}"


def _with_frontmatter(doc: dict) -> str:
    """Markdown 머리에 YAML 프런트매터로 출처·제목을 남긴다(AI 가 문맥을 잡기 좋다)."""
    src = doc["source"]
    meta = doc.get("metadata", {})
    lines = ["---", f"source_file: {_yaml(src['file_name'])}", f"format: {src['format']}"]
    for k in ("title", "author", "created", "modified"):
        if meta.get(k):
            lines.append(f"{k}: {_yaml(str(meta[k]))}")
    lines += [f"converted_at: {src['converted_at']}", f"sha256: {src['sha256']}", "---", ""]
    return "\n".join(lines) + doc["markdown"].rstrip() + "\n"


def _yaml(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)

"""Convert local HWP and HWPX documents to Markdown."""
from __future__ import annotations

import json
from pathlib import Path

from .schema import Converted


class HwpLocked(Exception):
    """암호·배포용(DRM) 문서라 본문을 읽을 수 없음."""


def convert_hwp(path: Path, image_prefix: str) -> Converted:
    import unhwp  # Load the native library only when converting a Hancom document.

    opts = unhwp.RenderOptions(
        image_path_prefix=image_prefix,
        table_fallback="markdown",
        include_frontmatter=False,
        preserve_line_breaks=True,
        escape_special_chars=True,
        section_markers="none",
        refine=False,
    )
    try:
        result = unhwp.parse(str(path), render_options=opts)
    except unhwp.UnsupportedFormatError as e:
        raise ValueError(f"HWP 형식을 인식하지 못했습니다: {e}") from e
    except unhwp.UnhwpError as e:
        msg = str(e).lower()
        if "password" in msg or "encrypt" in msg or "distribution" in msg or "암호" in msg:
            raise HwpLocked(str(e)) from e
        raise

    with result:
        warnings: list[str] = []
        try:
            meta_all = json.loads(result.json)
            metadata = meta_all.get("metadata", {}) or {}
        except Exception:  # noqa: BLE001 - 메타데이터는 없어도 변환은 계속
            metadata = {"title": result.title, "author": result.author}
        if getattr(result, "is_distribution", False):
            warnings.append("배포용 문서입니다. 일부 내용이 비어 있을 수 있습니다.")
        markdown = result.markdown or ""
        if not markdown.strip():
            if result.is_distribution:
                raise HwpLocked("배포용(DRM) 문서")
            warnings.append("본문 글자를 찾지 못했습니다. 그림만 있는 문서일 수 있습니다.")
        images = [(img.name, bytes(img.data)) for img in result.iter_images()]
    return Converted(markdown=markdown, engine=f"unhwp {unhwp.__version__}" if hasattr(unhwp, "__version__") else "unhwp",
                     metadata=_clean(metadata), images=images, warnings=warnings)


def _clean(meta: dict) -> dict:
    keep = ("title", "author", "subject", "keywords", "created", "modified", "creator_app", "format_version")
    return {k: meta.get(k) for k in keep if meta.get(k) not in (None, "", [])}

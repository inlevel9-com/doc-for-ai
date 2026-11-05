"""Convert older document formats using an optional local converter."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ..paths import app_dir

LEGACY_TARGET = {"doc": "docx", "ppt": "pptx", "rtf": "docx", "odt": "docx", "odp": "pptx", "ods": "xlsx"}


class LegacyPackMissing(Exception):
    pass


def find_soffice() -> Path | None:
    candidates = [
        app_dir() / "tools" / "LibreOffice" / "program" / "soffice.exe",
        app_dir() / "tools" / "LibreOfficePortable" / "App" / "libreoffice" / "program" / "soffice.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "LibreOffice" / "program" / "soffice.exe",
        Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
        Path("/usr/bin/soffice"),
        Path("/usr/lib/libreoffice/program/soffice"),
    ]
    for c in candidates:
        if c.exists():
            return c
    w = shutil.which("soffice") or shutil.which("libreoffice")
    return Path(w) if w else None


def convert_legacy(path: Path, fmt: str, workdir: Path | None = None) -> Path:
    """구형 파일을 현대 형식으로 바꿔 임시 파일 경로를 돌려준다."""
    target = LEGACY_TARGET[fmt]
    soffice = find_soffice()
    if soffice is None:
        raise LegacyPackMissing(
            f".{fmt} 같은 구형 문서는 '구형 문서 확장팩(LibreOffice)'이 있어야 변환됩니다. "
            "docs/OFFLINE.md 의 안내대로 tools/LibreOffice 폴더를 넣어 주세요."
        )
    workdir = workdir or Path(tempfile.mkdtemp(prefix="docforai_"))
    env = dict(os.environ)
    # 사용자 프로필이 잠겨 있어도 동작하도록 전용 프로필 사용
    profile = (workdir / "lo_profile").resolve()
    cmd = [
        str(soffice), "--headless", "--norestore", "--nologo",
        f"-env:UserInstallation={profile.as_uri()}",
        "--convert-to", target, "--outdir", str(workdir), str(path),
    ]
    creation = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0  # type: ignore[attr-defined]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300, env=env, creationflags=creation)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("LibreOffice 변환이 5분 안에 끝나지 않았습니다.") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"LibreOffice 변환 실패: {e.stderr.decode(errors='ignore')[:300]}") from e
    out = workdir / f"{path.stem}.{target}"
    if not out.exists():
        raise RuntimeError("LibreOffice 가 결과 파일을 만들지 못했습니다.")
    return out

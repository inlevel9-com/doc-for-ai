"""Resolve application and resource paths for packaged and source installs."""
from __future__ import annotations

import sys
from pathlib import Path


def app_dir() -> Path:
    """실행 파일(또는 프로젝트 루트)이 있는 폴더. 확장팩·설정 파일은 이 아래에서 찾는다."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bundle_dir() -> Path:
    """Return the bundled resource directory or the source package directory."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

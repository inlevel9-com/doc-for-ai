"""사용자 설정. 지금은 '새 버전 확인' 켜고 끄기 하나뿐이다.

저장 위치는 사용자 폴더 안(Windows: %APPDATA%\\docforai, Mac: ~/Library/Application Support/docforai)이라
배포 폴더를 어디로 옮겨도 유지되고, 읽기 전용 위치에서 실행해도 문제없다. 파일이 없거나 깨지면 기본값을 쓴다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAULTS: dict[str, object] = {"check_updates": True}


def settings_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "docforai" / "settings.json"


def load_settings() -> dict[str, object]:
    data = dict(DEFAULTS)
    try:
        loaded = json.loads(settings_path().read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data.update({k: v for k, v in loaded.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return data


def save_settings(data: dict[str, object]) -> None:
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({k: data.get(k, v) for k, v in DEFAULTS.items()}, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # 설정을 못 저장해도 프로그램은 계속 쓸 수 있어야 한다

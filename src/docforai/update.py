"""새 버전 확인과 배포 파일 내려받기.

이 프로그램이 인터넷에 닿는 곳은 여기뿐이다. GitHub Releases 에서 최신 태그를 읽어 지금 버전과 비교하고,
사용자가 누르면 이 PC에 맞는 ZIP 을 내려받기 폴더에 저장한다. 실행 파일을 스스로 바꿔치기하지는 않는다.
설정(`check_updates`)으로 끌 수 있고, 폐쇄망처럼 연결이 안 되면 아무 일도 하지 않고 조용히 넘어간다.
"""
from __future__ import annotations

import json
import platform
import re
import ssl
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import __version__

REPO = "inlevel9-com/doc-for-ai"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
TIMEOUT_SECONDS = 4
_VERSION_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


@dataclass
class UpdateInfo:
    version: str  # 예: "1.2.0"
    page_url: str
    asset_name: str | None = None  # 이 PC에 맞는 ZIP 이름
    asset_url: str | None = None


def parse_version(text: str) -> tuple[int, int, int]:
    m = _VERSION_RE.search(text or "")
    if not m:
        return (0, 0, 0)
    return tuple(int(g or 0) for g in m.groups())  # type: ignore[return-value]


def is_newer(latest: str, current: str = __version__) -> bool:
    return parse_version(latest) > parse_version(current)


def asset_suffix() -> str | None:
    """이 PC에 맞는 배포 파일 이름 끝. 맞는 파일이 없는 환경이면 None."""
    machine = platform.machine().lower()
    if sys.platform == "win32" and machine in ("amd64", "x86_64"):
        return "-windows-x64.zip"
    if sys.platform == "darwin" and machine == "arm64":
        return "-macos-arm64.zip"
    return None


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        import certifi  # 번들된 Python 에 시스템 인증서가 없을 때를 대비

        ctx.load_verify_locations(certifi.where())
    except Exception:  # noqa: BLE001
        pass
    return ctx


def _open(url: str, timeout: float = TIMEOUT_SECONDS):  # noqa: ANN202
    req = urllib.request.Request(url, headers={"User-Agent": f"docforai/{__version__}", "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout, context=_ssl_context())  # noqa: S310 - 고정된 GitHub 주소만 연다


def check_latest(timeout: float = TIMEOUT_SECONDS) -> UpdateInfo | None:
    """지금보다 새 버전이 있으면 그 정보를, 없거나 확인할 수 없으면 None 을 돌려준다. 예외를 밖으로 내지 않는다."""
    try:
        with _open(API_LATEST, timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - 오프라인·차단·형식 오류 모두 "확인 불가"
        return None
    return pick_update(data)


def pick_update(release: dict, current: str = __version__) -> UpdateInfo | None:
    """GitHub 릴리스 JSON 에서 새 버전 정보를 고른다(네트워크 없이 테스트 가능)."""
    tag = str(release.get("tag_name") or "")
    if not tag or release.get("draft") or release.get("prerelease") or not is_newer(tag, current):
        return None
    info = UpdateInfo(version=tag.lstrip("vV"), page_url=str(release.get("html_url") or RELEASES_PAGE))
    suffix = asset_suffix()
    for asset in release.get("assets") or []:
        name = str(asset.get("name") or "")
        if suffix and name.startswith("docforai-") and name.endswith(suffix):
            info.asset_name, info.asset_url = name, asset.get("browser_download_url")
            break
    return info


def downloads_dir() -> Path:
    d = Path.home() / "Downloads"
    return d if d.is_dir() else Path.home()


def download_asset(info: UpdateInfo, progress: Callable[[int, int], None] | None = None) -> Path:
    """ZIP 을 내려받기 폴더에 저장하고 경로를 돌려준다. 같은 이름이 있으면 덮어쓴다."""
    if not info.asset_url or not info.asset_name:
        raise RuntimeError("이 PC에 맞는 배포 파일이 없습니다. 릴리스 페이지에서 직접 받아 주세요.")
    target = downloads_dir() / info.asset_name
    part = target.with_suffix(".zip.part")
    with _open(info.asset_url, timeout=30) as resp, part.open("wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    part.replace(target)
    return target

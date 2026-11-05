"""새 버전 확인 테스트. 네트워크 없이 돌아야 하며, 연결이 막혀도 조용히 None 이어야 한다."""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from docforai import update
from docforai.settings import load_settings, save_settings, settings_path


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def guard(*a, **k):
        raise AssertionError("네트워크 접근 시도")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)


def test_version_compare():
    assert update.parse_version("v1.2.0") == (1, 2, 0)
    assert update.parse_version("2") == (2, 0, 0)
    assert update.is_newer("v1.2.0", "1.1.0")
    assert not update.is_newer("v1.1.0", "1.1.0")
    assert not update.is_newer("v1.0.9", "1.1.0")
    assert not update.is_newer("garbage", "1.1.0")


def test_check_latest_is_silent_when_offline():
    assert update.check_latest(timeout=0.5) is None


def _release(tag: str, **extra) -> dict:
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/inlevel9-com/doc-for-ai/releases/tag/{tag}",
        "assets": [
            {"name": f"docforai-{tag}-windows-x64.zip", "browser_download_url": "https://example.invalid/win.zip"},
            {"name": f"docforai-{tag}-macos-arm64.zip", "browser_download_url": "https://example.invalid/mac.zip"},
        ],
        **extra,
    }


def test_pick_update_chooses_matching_asset(monkeypatch):
    monkeypatch.setattr(update, "asset_suffix", lambda: "-macos-arm64.zip")
    info = update.pick_update(_release("v9.0.0"), current="1.1.0")
    assert info and info.version == "9.0.0"
    assert info.asset_name == "docforai-v9.0.0-macos-arm64.zip"
    assert info.asset_url == "https://example.invalid/mac.zip"


def test_pick_update_ignores_old_draft_and_prerelease(monkeypatch):
    monkeypatch.setattr(update, "asset_suffix", lambda: "-windows-x64.zip")
    assert update.pick_update(_release("v1.1.0"), current="1.1.0") is None
    assert update.pick_update(_release("v9.0.0", draft=True), current="1.1.0") is None
    assert update.pick_update(_release("v9.0.0", prerelease=True), current="1.1.0") is None


def test_pick_update_without_matching_asset_keeps_page(monkeypatch):
    monkeypatch.setattr(update, "asset_suffix", lambda: None)
    info = update.pick_update(_release("v9.0.0"), current="1.1.0")
    assert info and info.asset_url is None and info.page_url.endswith("v9.0.0")


def test_settings_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("docforai.settings.settings_path", lambda: tmp_path / "s" / "settings.json")
    assert load_settings() == {"check_updates": True}
    save_settings({"check_updates": False, "unknown": 1})
    assert json.loads((tmp_path / "s" / "settings.json").read_text(encoding="utf-8")) == {"check_updates": False}
    assert load_settings() == {"check_updates": False}
    (tmp_path / "s" / "settings.json").write_text("not json", encoding="utf-8")
    assert load_settings() == {"check_updates": True}

"""hwp → hwpx 저장(한컴오피스 한글 자동화) 테스트. 한글이 없는 PC에서도 돌아야 하므로 COM 은 가짜로 대신한다."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from docforai.engine import ConvertOptions, convert_file, convert_many
from docforai.engine.hancom import HancomMissing, HancomSession, unavailable_reason
from docforai.engine.schema import Converted


class FakeHwp:
    """한글 COM 개체 흉내: Open → SaveAs → Clear 순서와 인자를 기록한다."""

    def __init__(self, fail_open: bool = False) -> None:
        self.calls: list[tuple] = []
        self.fail_open = fail_open

    def Open(self, path: str, fmt: str, arg: str) -> bool:  # noqa: N802
        self.calls.append(("Open", path, fmt, arg))
        return not self.fail_open

    def SaveAs(self, path: str, fmt: str, arg: str) -> bool:  # noqa: N802
        self.calls.append(("SaveAs", path, fmt, arg))
        Path(path).write_bytes(b"PK\x03\x04 fake hwpx")
        return True

    def Clear(self, option: int) -> None:  # noqa: N802
        self.calls.append(("Clear", option))

    def Quit(self) -> None:  # noqa: N802
        self.calls.append(("Quit",))


def _fake_hwp_file(tmp_path: Path) -> Path:
    src = tmp_path / "공문.hwp"
    src.write_bytes(b"\xd0\xcf\x11\xe0" + b"\0" * 64)  # HWP 5 (OLE) 머리
    return src


@pytest.mark.skipif(sys.platform == "win32", reason="Windows 에서는 설치 여부에 따라 달라진다")
def test_unavailable_outside_windows():
    assert unavailable_reason() is not None
    with pytest.raises(HancomMissing):
        HancomSession().save_as_hwpx(Path("a.hwp"), Path("a.hwpx"))


def test_session_saves_and_closes_document(tmp_path: Path):
    fake = FakeHwp()
    session = HancomSession()
    session._hwp = fake
    src = _fake_hwp_file(tmp_path)
    target = tmp_path / "변환결과" / "공문.hwpx"
    assert session.save_as_hwpx(src, target) == target
    assert target.exists()
    assert [c[0] for c in fake.calls] == ["Open", "SaveAs", "Clear"]
    assert fake.calls[0][1:] == (str(src), "HWP", "forceopen:true")
    assert fake.calls[1][1:] == (str(target), "HWPX", "")
    session.close()
    assert fake.calls[-1] == ("Quit",)


def test_session_reports_open_failure(tmp_path: Path):
    session = HancomSession()
    session._hwp = FakeHwp(fail_open=True)
    with pytest.raises(RuntimeError, match="열지 못했습니다"):
        session.save_as_hwpx(_fake_hwp_file(tmp_path), tmp_path / "x.hwpx")


def test_convert_adds_hwpx_output(tmp_path: Path, monkeypatch):
    import docforai.engine as engine

    monkeypatch.setattr(engine, "_convert", lambda *a, **k: Converted(markdown="# 공문\n\n본문", engine="fake"))
    src = _fake_hwp_file(tmp_path)
    session = HancomSession()
    session._hwp = FakeHwp()
    r = convert_file(src, ConvertOptions(save_hwpx=True), hancom=session)
    assert r.ok, r.message
    assert "hwpx 저장" in r.message
    assert (tmp_path / "변환결과" / "공문.hwpx") in r.outputs
    assert not r.warnings


@pytest.mark.skipif(sys.platform == "win32", reason="Windows 에서는 설치 여부에 따라 달라진다")
def test_convert_keeps_markdown_when_hancom_missing(tmp_path: Path, monkeypatch):
    import docforai.engine as engine

    monkeypatch.setattr(engine, "_convert", lambda *a, **k: Converted(markdown="# 공문", engine="fake"))
    src = _fake_hwp_file(tmp_path)
    results = convert_many([src], ConvertOptions(save_hwpx=True))
    assert results[0].ok
    assert any("hwpx 저장 건너뜀" in w for w in results[0].warnings)
    assert not (tmp_path / "변환결과" / "공문.hwpx").exists()


def test_hwpx_option_ignored_for_other_formats(tmp_path: Path, monkeypatch):
    import docforai.engine as engine

    monkeypatch.setattr(engine, "_convert", lambda *a, **k: Converted(markdown="글", engine="fake"))
    src = tmp_path / "메모.txt"
    src.write_text("글", encoding="utf-8")
    r = convert_file(src, ConvertOptions(save_hwpx=True))
    assert r.ok and "hwpx" not in r.message and not r.warnings

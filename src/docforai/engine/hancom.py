"""한컴오피스 한글로 .hwp 를 .hwpx 로 저장한다(선택 기능).

한글 자동화(COM, `HWPFrame.HwpObject`)를 쓰므로 **Windows + 한컴오피스 한글(2018 이상 권장)** 이
설치된 PC에서만 켜진다. 설치돼 있지 않으면 `is_available()` 이 False 를 돌려주고 기능은 조용히 꺼진다.
서식을 그대로 보존한 hwpx 를 만드는 방법은 한글 자체로 다시 저장하는 것뿐이라 이 경로를 쓴다.
네트워크는 어디서도 쓰지 않는다.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

HWPX_SOURCE_FORMATS = {"hwp"}  # hwpx 는 이미 hwpx 이고, hwt·hml 은 서식 파일·XML 이라 제외
HWP_PROGIDS = ("HWPFrame.HwpObject", "HWPFrame.HwpObject.1")


class HancomMissing(Exception):
    """한컴오피스 한글이 없는 PC."""


def unavailable_reason() -> str | None:
    """이 PC에서 hwpx 저장을 쓸 수 없는 이유. 쓸 수 있으면 None."""
    if sys.platform != "win32":
        return "hwpx 저장은 Windows 에서만 됩니다"
    try:
        import winreg
    except ImportError:  # pragma: no cover - Windows 에는 항상 있다
        return "Windows 레지스트리를 읽을 수 없습니다"
    for progid in HWP_PROGIDS:
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid):
                return None
        except OSError:
            continue
    return "이 PC에 한컴오피스 한글이 설치되어 있지 않습니다"


def is_available() -> bool:
    return unavailable_reason() is None


class HancomSession:
    """한 번의 일괄 작업 동안 한글 인스턴스를 하나만 띄워 재사용한다.

    COM 개체는 만든 스레드에서만 써야 하므로, 변환 작업 스레드 안에서 만들고 같은 스레드에서 닫는다.
    """

    def __init__(self) -> None:
        self._hwp: Any = None
        self._com: Any = None

    def __enter__(self) -> "HancomSession":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _ensure(self) -> Any:
        if self._hwp is not None:
            return self._hwp
        reason = unavailable_reason()
        if reason:
            raise HancomMissing(reason)
        import pythoncom  # type: ignore[import-not-found]
        import win32com.client  # type: ignore[import-not-found]

        pythoncom.CoInitialize()
        self._com = pythoncom
        hwp = win32com.client.Dispatch(HWP_PROGIDS[0])
        # 한글 자동화 보안 모듈이 등록된 PC에서는 파일 접근 확인 창이 뜨지 않는다. 없으면 그냥 넘어간다.
        try:
            hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        except Exception:  # noqa: BLE001
            pass
        try:
            hwp.XHwpWindows.Item(0).Visible = False
        except Exception:  # noqa: BLE001
            pass
        self._hwp = hwp
        return hwp

    def save_as_hwpx(self, source: Path, target: Path) -> Path:
        """source(.hwp) 를 한글로 열어 target(.hwpx) 으로 저장한다."""
        hwp = self._ensure()
        source, target = Path(source), Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not hwp.Open(str(source), "HWP", "forceopen:true"):
            raise RuntimeError("한글이 문서를 열지 못했습니다 (암호·배포용 문서일 수 있음)")
        try:
            if not hwp.SaveAs(str(target), "HWPX", ""):
                raise RuntimeError("한글이 HWPX 로 저장하지 못했습니다")
        finally:
            try:
                hwp.Clear(1)  # 1 = 저장하지 않고 문서 닫기
            except Exception:  # noqa: BLE001
                pass
        if not target.exists():
            raise RuntimeError("한글이 HWPX 파일을 만들지 못했습니다")
        return target

    def close(self) -> None:
        if self._hwp is not None:
            try:
                self._hwp.Quit()
            except Exception:  # noqa: BLE001
                pass
            self._hwp = None
        if self._com is not None:
            try:
                self._com.CoUninitialize()
            except Exception:  # noqa: BLE001
                pass
            self._com = None

"""Build the portable desktop app as a directory."""

import platform
import sys
from importlib.metadata import version as dist_version
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, copy_metadata

ROOT = Path(SPECPATH).parent
native_platform = (platform.system(), platform.machine().lower())
runtime_id = {
    ("Windows", "amd64"): "win-x64",
    ("Windows", "x86_64"): "win-x64",
    ("Darwin", "arm64"): "osx-arm64",
    ("Darwin", "x86_64"): "osx-x64",
}.get(native_platform)

# Keep the platform-specific library at the path used by the runtime loader.
hwp_binaries = [
    (source, destination)
    for source, destination in collect_dynamic_libs("unhwp")
    if Path(destination).name == runtime_id
]
if not hwp_binaries:
    raise SystemExit(f"No native HWP parser library found for {native_platform}")

sys.path.insert(0, str(ROOT / "src"))
from docforai import APP_NAME, DESIGNED_BY, PRODUCT_NAME  # noqa: E402

ASSETS = ROOT / "src" / "docforai" / "assets"
APP_VERSION = dist_version("docforai")

# Windows 탐색기의 파일 속성(제품명·버전·회사)에 표시되는 정보. macOS는 .app 번들 정보로 대신한다.
exe_icon = None
version_info = None
MAC_APP_NAME = f"{APP_NAME}.app"
if platform.system() == "Windows":
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
    )

    numbers = [int(part) for part in APP_VERSION.split(".")[:3]] + [0]
    while len(numbers) < 4:
        numbers.append(0)
    exe_icon = str(ASSETS / "icon.ico")
    version_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=tuple(numbers), prodvers=tuple(numbers)),
        kids=[
            StringFileInfo([StringTable("041204B0", [
                StringStruct("CompanyName", "INLEVEL9"),
                StringStruct("FileDescription", PRODUCT_NAME),
                StringStruct("FileVersion", APP_VERSION),
                StringStruct("InternalName", "docforai"),
                StringStruct("OriginalFilename", "docforai.exe"),
                StringStruct("ProductName", PRODUCT_NAME),
                StringStruct("ProductVersion", APP_VERSION),
                StringStruct("LegalCopyright", f"{DESIGNED_BY}. Apache License 2.0"),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0412, 1200])]),
        ],
    )

analysis = Analysis(
    [str(ROOT / "src" / "docforai" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=hwp_binaries,
    datas=copy_metadata("mammoth") + copy_metadata("markdownify") + [(str(ASSETS), "docforai/assets")],
    # Pillow 플러그인(JPEG/PNG/GIF/BMP/TIFF/WebP)은 PyInstaller 훅이 모으지만 명시해 둔다.
    hiddenimports=["PIL.JpegImagePlugin", "PIL.PngImagePlugin", "PIL.GifImagePlugin", "PIL.BmpImagePlugin",
                   "PIL.TiffImagePlugin", "PIL.WebPImagePlugin", "tinytag"],
)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="docforai", console=False, upx=False,
          icon=exe_icon, version=version_info)
bundle = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name="docforai")

if platform.system() == "Darwin":
    app = BUNDLE(
        bundle,
        name=MAC_APP_NAME,
        icon=str(ASSETS / "icon.icns"),
        bundle_identifier="com.inlevel9.docforai",
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "NSHumanReadableCopyright": f"{DESIGNED_BY}. Apache License 2.0",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.productivity",
        },
    )

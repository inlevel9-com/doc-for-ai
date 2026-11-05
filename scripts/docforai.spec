"""Build the portable desktop app as a directory."""

import platform
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

analysis = Analysis(
    [str(ROOT / "src" / "docforai" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=hwp_binaries,
    datas=copy_metadata("mammoth") + copy_metadata("markdownify"),
    # Pillow 플러그인(JPEG/PNG/GIF/BMP/TIFF/WebP)은 PyInstaller 훅이 모으지만 명시해 둔다.
    hiddenimports=["PIL.JpegImagePlugin", "PIL.PngImagePlugin", "PIL.GifImagePlugin", "PIL.BmpImagePlugin",
                   "PIL.TiffImagePlugin", "PIL.WebPImagePlugin", "tinytag"],
)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="docforai", console=False, upx=False)
bundle = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name="docforai")

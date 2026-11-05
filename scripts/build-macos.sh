#!/usr/bin/env bash
# macOS(Apple Silicon)용 배포 ZIP을 만든다. 사용법: ./scripts/build-macos.sh  (PYTHON=python3.12 로 인터프리터 지정 가능)
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"

"$PYTHON" -c 'import platform, sys; sys.exit(0 if sys.platform == "darwin" and platform.machine() == "arm64" and sys.version_info[:2] >= (3, 12) else "macOS arm64 Python 3.12 or newer is required")'
"$PYTHON" -c 'import tkinter' || { echo "This Python has no Tk. Install python.org Python or Homebrew python-tk." >&2; exit 1; }

# 개발 환경의 패키지가 섞이지 않도록 빈 가상환경에서 빌드한다.
"$PYTHON" -m venv --clear build/venv
BUILD_PYTHON=build/venv/bin/python
PIP_OPTIONS=(--disable-pip-version-check)
if [ -d wheelhouse ]; then
    PIP_OPTIONS+=(--no-index --find-links wheelhouse)
fi
"$BUILD_PYTHON" -m pip install "${PIP_OPTIONS[@]}" ".[build]"

rm -rf dist/docforai "dist/AI 문서 변환기.app"
"$BUILD_PYTHON" -m PyInstaller scripts/docforai.spec --noconfirm --distpath dist --workpath build/pyinstaller

# PyInstaller 는 폴더(dist/docforai)와 .app 을 둘 다 만든다. 배포에는 .app 만 담는다.
BUNDLE=dist/docforai
rm -rf "$BUNDLE"
mkdir -p "$BUNDLE"
mv "dist/AI 문서 변환기.app" "$BUNDLE/"
cp LICENSE README.md docs/usage.txt "$BUNDLE/"
cp -R docs "$BUNDLE/docs"
"$BUILD_PYTHON" scripts/collect-licenses.py "$BUNDLE/licenses"
mkdir -p "$BUNDLE/tools"
printf 'See docs/OFFLINE.md for optional LibreOffice support.\n' > "$BUNDLE/tools/README.txt"

VERSION=$("$BUILD_PYTHON" -c "from importlib.metadata import version; print(version('docforai'))")
ARCHIVE="dist/docforai-v${VERSION}-macos-arm64.zip"
rm -f "$ARCHIVE"
# ditto 는 .app 안의 심볼릭 링크와 실행 권한을 그대로 보존한다.
ditto -c -k --keepParent "$BUNDLE" "$ARCHIVE"
echo "Built $ARCHIVE"

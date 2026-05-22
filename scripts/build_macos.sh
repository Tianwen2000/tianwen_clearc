#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON="${PYTHON:-.venv/bin/python}"
APP_NAME="Tianwen ClearC"
ICON_FILE="tianwen_clearc.icns"
RELEASE_DIR="release"

if [[ ! -x "$PYTHON" ]]; then
  echo "[ERROR] Python not found: $PYTHON" >&2
  echo "Create the virtual environment and install dependencies first." >&2
  exit 1
fi

if [[ ! -f "$ICON_FILE" ]]; then
  echo "[ERROR] Missing icon file: $ICON_FILE" >&2
  exit 1
fi

"$PYTHON" -m pip install -e . >/dev/null
rm -rf build dist "${APP_NAME}.spec"

"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --icon "$ICON_FILE" \
  --paths src \
  src/tianwen_clearc/app.py

rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"
cp -R "dist/${APP_NAME}.app" "${RELEASE_DIR}/${APP_NAME}.app"

ditto -c -k --keepParent "${RELEASE_DIR}/${APP_NAME}.app" \
  "${RELEASE_DIR}/Tianwen_ClearC_macOS_arm64.zip"

hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "${RELEASE_DIR}/${APP_NAME}.app" \
  -ov \
  -format UDZO \
  "${RELEASE_DIR}/Tianwen_ClearC_macOS_arm64.dmg"

(cd .. && zip -r "tianwen_clearC/${RELEASE_DIR}/tianwen_clearC_20260521_152516.zip" tianwen_clearC \
  -x 'tianwen_clearC/.venv/*' \
  -x 'tianwen_clearC/.ruff_cache/*' \
  -x 'tianwen_clearC/.pytest_cache/*' \
  -x 'tianwen_clearC/.DS_Store' \
  -x 'tianwen_clearC/**/.DS_Store' \
  -x 'tianwen_clearC/__pycache__/*' \
  -x 'tianwen_clearC/**/__pycache__/*' \
  -x 'tianwen_clearC/*.pyc' \
  -x 'tianwen_clearC/**/*.pyc' \
  -x 'tianwen_clearC/build/*' \
  -x 'tianwen_clearC/dist/*' \
  -x 'tianwen_clearC/release/*' \
  -x 'tianwen_clearC/src/*.egg-info/*' \
  -x 'tianwen_clearC/tianwen_clearc_app.log' \
  -x 'tianwen_clearC/tianwen_clearc_app.pid' \
  -x 'tianwen_clearC/Tianwen ClearC.spec')

echo "Build finished:"
echo "${RELEASE_DIR}/${APP_NAME}.app"
echo "${RELEASE_DIR}/Tianwen_ClearC_macOS_arm64.zip"
echo "${RELEASE_DIR}/Tianwen_ClearC_macOS_arm64.dmg"
echo "${RELEASE_DIR}/tianwen_clearC_20260521_152516.zip"

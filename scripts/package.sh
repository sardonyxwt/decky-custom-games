#!/usr/bin/env bash
# Builds out/custom-games.zip for Decky → Developer → "Install plugin from ZIP".
set -euo pipefail
cd "$(dirname "$0")/.."
pnpm run build
rm -rf out && mkdir -p out/custom-games/py_modules
cp -r dist main.py plugin.json package.json LICENSE README.md out/custom-games/
cp -r py_modules/customgames out/custom-games/py_modules/
rm -f out/custom-games/dist/*.map
find out -name __pycache__ -prune -exec rm -rf {} +
(cd out && zip -qr custom-games.zip custom-games)
echo "out/custom-games.zip"

#!/bin/bash
# Dvojklikem spustí administraci katalogu (macOS). Používá systémový Python a doinstaluje chybějící balíčky.
cd "$(dirname "$0")/.."
PY=/usr/bin/python3
$PY -c "import fastapi, uvicorn, multipart, PIL, fitz, openpyxl" 2>/dev/null || {
  echo "Instaluji potřebné balíčky…"
  $PY -m pip install --user -q fastapi "uvicorn[standard]" python-multipart pillow pymupdf openpyxl
}
[ -f admin/katalog.sqlite ] || $PY admin/import_catalog.py
exec $PY admin/app.py

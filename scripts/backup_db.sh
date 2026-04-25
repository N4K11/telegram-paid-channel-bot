#!/bin/sh
set -eu

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

DB_PATH="${DB_PATH:-data/db.json}"
BACKUP_DIR="${BACKUP_DIR:-data/backups}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_PATH="$BACKUP_DIR/db.$TIMESTAMP.json"

if [ ! -f "$DB_PATH" ]; then
  echo "Store file not found: $DB_PATH" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
cp "$DB_PATH" "$BACKUP_PATH"

if ! "$PYTHON_BIN" - "$BACKUP_PATH" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    json.load(handle)
PY
then
  rm -f "$BACKUP_PATH"
  echo "Backup validation failed: $BACKUP_PATH" >&2
  exit 1
fi

echo "Created backup: $BACKUP_PATH"
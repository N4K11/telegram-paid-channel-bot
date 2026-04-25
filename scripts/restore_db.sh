#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

DB_PATH="${DB_PATH:-data/db.json}"
BACKUP_DIR="${BACKUP_DIR:-data/backups}"

usage() {
  echo "Usage: $0 <backup-file> --yes" >&2
  exit 1
}

if [ "$#" -ne 2 ]; then
  usage
fi

BACKUP_SOURCE="$1"
CONFIRM="$2"

if [ "$CONFIRM" != "--yes" ]; then
  echo "Refusing to restore without explicit confirmation flag --yes." >&2
  usage
fi

if [ ! -f "$BACKUP_SOURCE" ]; then
  echo "Backup file not found: $BACKUP_SOURCE" >&2
  exit 1
fi

sh "$SCRIPT_DIR/verify_backup.sh" "$BACKUP_SOURCE"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
SAFETY_BACKUP="$BACKUP_DIR/db.pre-restore.$TIMESTAMP.json"
TEMP_RESTORE_PATH="$DB_PATH.restore.tmp"

mkdir -p "$(dirname -- "$DB_PATH")"
mkdir -p "$BACKUP_DIR"

if [ -f "$DB_PATH" ]; then
  cp "$DB_PATH" "$SAFETY_BACKUP"
  echo "Created safety backup: $SAFETY_BACKUP"
fi

cp "$BACKUP_SOURCE" "$TEMP_RESTORE_PATH"
"$PYTHON_BIN" - "$TEMP_RESTORE_PATH" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    json.load(handle)
PY
mv "$TEMP_RESTORE_PATH" "$DB_PATH"

echo "Restore completed: $DB_PATH"
#!/bin/sh
set -eu

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <backup-file>" >&2
  exit 1
fi

BACKUP_PATH="$1"

if [ ! -f "$BACKUP_PATH" ]; then
  echo "Backup file not found: $BACKUP_PATH" >&2
  exit 1
fi

"$PYTHON_BIN" - "$BACKUP_PATH" <<'PY'
import json
import sys

required_types = {
    "meta": dict,
    "settings": dict,
    "users": dict,
    "payments": dict,
    "auditLog": list,
}

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

if not isinstance(payload, dict):
    raise SystemExit("Invalid backup root: expected JSON object")

for key, expected_type in required_types.items():
    if key not in payload:
        raise SystemExit(f"Missing required top-level key: {key}")
    if not isinstance(payload[key], expected_type):
        raise SystemExit(
            f"Invalid top-level key type for {key}: expected {expected_type.__name__}"
        )

if "messageTemplates" in payload["settings"] and not isinstance(
    payload["settings"]["messageTemplates"], dict
):
    raise SystemExit("Invalid settings.messageTemplates: expected object")
PY

echo "Backup verified: $BACKUP_PATH"
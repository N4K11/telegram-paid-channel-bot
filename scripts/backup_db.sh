#!/bin/sh
set -eu

DB_PATH="data/db.json"
BACKUP_DIR="data/backups"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_PATH="$BACKUP_DIR/db.$TIMESTAMP.json"

mkdir -p "$BACKUP_DIR"
cp "$DB_PATH" "$BACKUP_PATH"
echo "Created backup: $BACKUP_PATH"

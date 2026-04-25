#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_NAME="${SERVICE_NAME:-private-channel-bot}"

cd "$REPO_ROOT"

if [ ! -f .venv/bin/activate ]; then
  echo "Virtual environment not found: .venv/bin/activate" >&2
  exit 1
fi

if [ ! -x ./scripts/backup_db.sh ]; then
  echo "Backup script is missing or not executable: ./scripts/backup_db.sh" >&2
  exit 1
fi

git pull --ff-only
source .venv/bin/activate
pip install -r requirements.txt
python -m compileall .
python -m unittest discover -s tests -p "test_*.py" -v
./scripts/backup_db.sh
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager
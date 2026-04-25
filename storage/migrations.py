import json
import os
import shutil
import time

from storage.json_store import JsonStore
from storage.sqlite_store import SQLiteStore


def backup_json_store(json_path, backup_path=None):
    source_path = os.path.abspath(json_path)
    if not os.path.exists(source_path):
        raise RuntimeError(f"JSON store not found: {source_path}")

    timestamp = time.strftime('%Y%m%d-%H%M%S')
    if backup_path is None:
        directory = os.path.dirname(source_path) or '.'
        backup_path = os.path.join(directory, f"db.pre-sqlite-migration.{timestamp}.json")

    backup_path = os.path.abspath(backup_path)
    os.makedirs(os.path.dirname(backup_path) or '.', exist_ok=True)
    shutil.copy2(source_path, backup_path)

    try:
        with open(backup_path, 'r', encoding='utf-8') as handle:
            json.load(handle)
    except Exception:
        try:
            os.remove(backup_path)
        except OSError:
            pass
        raise

    return backup_path


def migrate_json_to_sqlite(json_path, sqlite_path, backup_path=None):
    json_path = os.path.abspath(json_path)
    sqlite_path = os.path.abspath(sqlite_path)
    if json_path == sqlite_path:
        raise RuntimeError('SQLite path must be different from JSON path')

    backup_result = backup_json_store(json_path, backup_path=backup_path)
    json_store = JsonStore(json_path)
    sqlite_store = SQLiteStore(sqlite_path)
    state = json_store.get_state()
    sqlite_store.replace_state(state)

    migrated_state = sqlite_store.get_state()
    return {
        'backupPath': backup_result,
        'sqlitePath': sqlite_path,
        'users': len(migrated_state.get('users', {})),
        'payments': len(migrated_state.get('payments', {})),
        'auditLog': len(migrated_state.get('auditLog', [])),
    }
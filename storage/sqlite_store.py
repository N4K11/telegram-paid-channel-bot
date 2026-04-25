import json
import os
import sqlite3
import threading
from contextlib import contextmanager

from store_py import JsonStore, create_default_state, merge_state
from utils_py import now_iso


class SQLiteStore(JsonStore):
    def __init__(self, file_path):
        self.file_path = file_path
        self.lock = threading.RLock()
        self._ensure_file()
        self.state = self._load()

    def _connect(self):
        connection = sqlite3.connect(self.file_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _ensure_file(self):
        directory = os.path.dirname(self.file_path) or "."
        os.makedirs(directory, exist_ok=True)

        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS store_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            row = connection.execute(
                "SELECT payload FROM store_state WHERE id = 1"
            ).fetchone()
            if row is None:
                default_state = create_default_state()
                connection.execute(
                    "INSERT INTO store_state (id, payload, updated_at) VALUES (1, ?, ?)",
                    (
                        json.dumps(default_state, ensure_ascii=False, indent=2),
                        default_state["meta"]["updatedAt"],
                    ),
                )
            connection.commit()

    def _load(self):
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT payload FROM store_state WHERE id = 1"
                ).fetchone()
        except sqlite3.Error as error:
            raise RuntimeError(f"Failed to read SQLite store {self.file_path}: {error}") from error

        if row is None:
            raise RuntimeError(f"SQLite store is missing state row in {self.file_path}")

        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Invalid JSON payload in SQLite store {self.file_path}: {error}") from error

        if not isinstance(payload, dict):
            raise RuntimeError(f"Invalid SQLite store root in {self.file_path}: expected JSON object")

        return merge_state(payload)

    def _save_unlocked(self):
        self.state["meta"]["updatedAt"] = now_iso()
        payload = json.dumps(self.state, ensure_ascii=False, indent=2)

        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE store_state SET payload = ?, updated_at = ? WHERE id = 1",
                    (payload, self.state["meta"]["updatedAt"]),
                )
                connection.commit()
        except sqlite3.Error as error:
            raise RuntimeError(f"Failed to write SQLite store {self.file_path}: {error}") from error

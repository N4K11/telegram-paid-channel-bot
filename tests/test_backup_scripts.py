import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from store_py import create_default_state


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / 'scripts'
BACKUP_SCRIPT = SCRIPTS_DIR / 'backup_db.sh'
RESTORE_SCRIPT = SCRIPTS_DIR / 'restore_db.sh'
VERIFY_SCRIPT = SCRIPTS_DIR / 'verify_backup.sh'
TOKEN_PATTERN = re.compile(r'\b\d{6,12}:[A-Za-z0-9_-]{20,}\b')


class BackupScriptsTests(unittest.TestCase):
    def _read_text(self, path):
        return path.read_text(encoding='utf-8-sig')

    def _ensure_sh(self):
        sh_path = shutil.which('sh')
        if not sh_path:
            self.skipTest('POSIX sh is not available on this host')
        return sh_path

    def _run_script(self, script_path, args=None, env=None):
        sh_path = self._ensure_sh()
        command = [sh_path, str(script_path)]
        if args:
            command.extend(args)
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=merged_env,
            capture_output=True,
            text=True,
            check=False,
        )

    def _write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    def test_backup_scripts_exist(self):
        self.assertTrue(BACKUP_SCRIPT.exists())
        self.assertTrue(RESTORE_SCRIPT.exists())
        self.assertTrue(VERIFY_SCRIPT.exists())

    def test_scripts_do_not_contain_windows_paths_or_tokens(self):
        for path in (BACKUP_SCRIPT, RESTORE_SCRIPT, VERIFY_SCRIPT):
            text = self._read_text(path)
            self.assertNotIn('C:\\', text)
            self.assertNotIn('D:\\', text)
            self.assertIsNone(TOKEN_PATTERN.search(text), msg=f'Real-looking token found in {path}')

    def test_restore_script_requires_argument_and_confirmation_in_source(self):
        text = self._read_text(RESTORE_SCRIPT)
        self.assertIn('Usage: $0 <backup-file> --yes', text)
        self.assertIn('Refusing to restore without explicit confirmation flag --yes.', text)
        self.assertIn('if [ "$#" -ne 2 ]; then', text)
        self.assertIn('if [ "$CONFIRM" != "--yes" ]; then', text)

    def test_backup_script_does_not_delete_db_in_source(self):
        text = self._read_text(BACKUP_SCRIPT)
        self.assertIn('cp "$DB_PATH" "$BACKUP_PATH"', text)
        self.assertNotIn('rm -f "$DB_PATH"', text)
        self.assertNotIn('rm "$DB_PATH"', text)

    def test_verify_script_does_not_modify_files_in_source(self):
        text = self._read_text(VERIFY_SCRIPT)
        self.assertNotIn('cp ', text)
        self.assertNotIn('mv ', text)
        self.assertNotIn('rm ', text)
        self.assertIn('json.load', text)

    def test_backup_script_creates_valid_backup_when_sh_available(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            db_path = tmp_path / 'data' / 'db.json'
            backup_dir = tmp_path / 'backups'
            initial_state = create_default_state()
            self._write_json(db_path, initial_state)

            result = self._run_script(
                BACKUP_SCRIPT,
                env={
                    'DB_PATH': str(db_path),
                    'BACKUP_DIR': str(backup_dir),
                },
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            backups = sorted(backup_dir.glob('db.*.json'))
            self.assertEqual(len(backups), 1)
            payload = json.loads(backups[0].read_text(encoding='utf-8'))
            self.assertIsInstance(payload, dict)
            self.assertEqual(json.loads(db_path.read_text(encoding='utf-8')), initial_state)

    def test_restore_script_requires_confirmation_when_sh_available(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            backup_path = tmp_path / 'backup.json'
            self._write_json(backup_path, create_default_state())

            result = self._run_script(RESTORE_SCRIPT, args=[str(backup_path)])

            self.assertNotEqual(result.returncode, 0)
            self.assertIn('--yes', result.stderr + result.stdout)

    def test_restore_script_restores_and_makes_safety_backup_when_sh_available(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            db_path = tmp_path / 'data' / 'db.json'
            backup_dir = tmp_path / 'backups'
            current_state = create_default_state()
            current_state['meta']['lastUpdateId'] = 111
            backup_state = create_default_state()
            backup_state['meta']['lastUpdateId'] = 222
            backup_path = tmp_path / 'restore-source.json'
            self._write_json(db_path, current_state)
            self._write_json(backup_path, backup_state)

            result = self._run_script(
                RESTORE_SCRIPT,
                args=[str(backup_path), '--yes'],
                env={
                    'DB_PATH': str(db_path),
                    'BACKUP_DIR': str(backup_dir),
                },
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            restored_state = json.loads(db_path.read_text(encoding='utf-8'))
            self.assertEqual(restored_state['meta']['lastUpdateId'], 222)
            safety_backups = sorted(backup_dir.glob('db.pre-restore.*.json'))
            self.assertEqual(len(safety_backups), 1)
            safety_state = json.loads(safety_backups[0].read_text(encoding='utf-8'))
            self.assertEqual(safety_state['meta']['lastUpdateId'], 111)

    def test_verify_script_is_read_only_when_sh_available(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            backup_path = tmp_path / 'backup.json'
            self._write_json(backup_path, create_default_state())
            before_content = backup_path.read_bytes()
            before_mtime = backup_path.stat().st_mtime_ns

            result = self._run_script(VERIFY_SCRIPT, args=[str(backup_path)])

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            after_content = backup_path.read_bytes()
            after_mtime = backup_path.stat().st_mtime_ns
            self.assertEqual(after_content, before_content)
            self.assertEqual(after_mtime, before_mtime)


if __name__ == '__main__':
    unittest.main()


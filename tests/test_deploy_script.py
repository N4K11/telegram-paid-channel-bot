import re
import shutil
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = REPO_ROOT / 'scripts' / 'deploy.sh'
TOKEN_PATTERN = re.compile(r'\b\d{6,12}:[A-Za-z0-9_-]{20,}\b')


class DeployScriptTests(unittest.TestCase):
    def _read_text(self):
        return DEPLOY_SCRIPT.read_text(encoding='utf-8-sig')

    def test_deploy_script_exists(self):
        self.assertTrue(DEPLOY_SCRIPT.exists())

    def test_deploy_script_has_safe_shell_options(self):
        text = self._read_text()
        self.assertIn('#!/usr/bin/env bash', text)
        self.assertIn('set -euo pipefail', text)

    def test_deploy_script_runs_tests_before_restart(self):
        text = self._read_text()
        compile_index = text.index('python -m compileall .')
        unittest_index = text.index('python -m unittest discover -s tests -p "test_*.py" -v')
        restart_index = text.index('sudo systemctl restart "$SERVICE_NAME"')

        self.assertLess(compile_index, restart_index)
        self.assertLess(unittest_index, restart_index)

    def test_deploy_script_runs_backup_before_restart(self):
        text = self._read_text()
        backup_index = text.index('./scripts/backup_db.sh')
        restart_index = text.index('sudo systemctl restart "$SERVICE_NAME"')
        self.assertLess(backup_index, restart_index)

    def test_deploy_script_has_no_secrets_or_windows_paths(self):
        text = self._read_text()
        self.assertNotIn('C:\\', text)
        self.assertNotIn('D:\\', text)
        self.assertIsNone(TOKEN_PATTERN.search(text))

    def test_deploy_script_is_bash_parseable_when_bash_available(self):
        bash_path = shutil.which('bash')
        if not bash_path:
            self.skipTest('bash is not available on this host')

        result = subprocess.run(
            [bash_path, '-n', str(DEPLOY_SCRIPT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)


if __name__ == '__main__':
    unittest.main()
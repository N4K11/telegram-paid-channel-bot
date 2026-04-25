import re
import unittest
from pathlib import Path


class GitHubActionsConfigTests(unittest.TestCase):
    def test_tests_workflow_exists(self):
        path = Path('.github/workflows/tests.yml')
        self.assertTrue(path.exists())

    def test_tests_workflow_has_required_steps(self):
        content = Path('.github/workflows/tests.yml').read_text(encoding='utf-8-sig')

        required_snippets = [
            'name: tests',
            'push:',
            'pull_request:',
            'actions/checkout@v4',
            'actions/setup-python@v5',
            'python-version: "3.11"',
            'python -m pip install --upgrade pip',
            'pip install -r requirements.txt',
            'python -m compileall .',
            'python -m unittest discover -s tests -p "test_*.py" -v',
        ]
        for snippet in required_snippets:
            self.assertIn(snippet, content)

    def test_tests_workflow_has_no_secrets(self):
        content = Path('.github/workflows/tests.yml').read_text(encoding='utf-8-sig')

        self.assertNotIn('secrets.', content)
        self.assertIsNone(re.search(r'\b\d{6,12}:[A-Za-z0-9_-]{20,}\b', content))

    def test_tests_workflow_has_no_deploy_steps(self):
        content = Path('.github/workflows/tests.yml').read_text(encoding='utf-8-sig')

        forbidden_snippets = [
            'systemctl ',
            'journalctl ',
            'ssh ',
            'scp ',
            'rsync ',
            'deploy.sh',
            'backup_db.sh',
            'restore_db.sh',
            'verify_backup.sh',
            'private-channel-bot.service',
        ]
        for snippet in forbidden_snippets:
            self.assertNotIn(snippet, content)


if __name__ == '__main__':
    unittest.main()

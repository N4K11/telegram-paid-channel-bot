import re
import unittest
from pathlib import Path


class OpsReadinessTests(unittest.TestCase):
    def test_deploy_ubuntu_doc_has_required_sections(self):
        path = Path('DEPLOY_UBUNTU.md')
        self.assertTrue(path.exists())
        content = path.read_text(encoding='utf-8-sig')

        required_snippets = [
            '# Ubuntu Deployment',
            '## 1. Server prerequisites',
            '/opt/private-channel-bot',
            'sudo adduser --system --group --home /opt/private-channel-bot botuser',
            'python3 -m venv .venv',
            'cp .env.example .env',
            'python -m compileall .',
            'python -m unittest discover -s tests -p "test_*.py" -v',
            'python main.py',
            '/etc/systemd/system/private-channel-bot.service',
            'WorkingDirectory=/opt/private-channel-bot',
            'ExecStart=/opt/private-channel-bot/.venv/bin/python /opt/private-channel-bot/main.py',
            'Restart=always',
            'EnvironmentFile=/opt/private-channel-bot/.env',
            'User=botuser',
            'journalctl -u private-channel-bot -f',
            '## 12. Backup db.json',
            '## 13. Rollback procedure',
            '## 14. Update procedure',
            '## 15. Common issues',
            'bot does not start',
            'missing env variable',
            'bot cannot approve join request',
            'bot cannot kick/revoke user',
            'Stars payment not arriving',
            'permission denied on data/db.json',
            'systemd service restart loop',
        ]
        for snippet in required_snippets:
            self.assertIn(snippet, content)

    def test_release_checklist_exists(self):
        path = Path('RELEASE_CHECKLIST.md')
        self.assertTrue(path.exists())
        content = path.read_text(encoding='utf-8-sig')

        required_items = [
            '## Before deploy',
            'Tests pass',
            'Bot token is valid',
            'Channel id is valid',
            'Bot is admin in the channel',
            'Bot has `invite users` permission',
            'Bot has `restrict members` permission',
            'Join requests are enabled if approve flow is required',
            'Admin Telegram id is configured',
            'Backup exists',
            'data/db.json',
            '## Manual smoke after deploy',
            '/start',
            '/admin',
            'Admin stats opens',
            'Buy invoice opens',
            'Successful payment activates subscription',
            'Join request approve works',
            'Payment anomalies command works',
            '## Rollback',
            'Stop the service',
            'Restore the previous code release',
            'Run tests',
        ]
        for item in required_items:
            self.assertIn(item, content)

    def test_env_example_has_required_keys(self):
        path = Path('.env.example')
        content = path.read_text(encoding='utf-8-sig')
        keys = {
            line.split('=', 1)[0].strip()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith('#') and '=' in line
        }

        expected_keys = {
            'TELEGRAM_BOT_TOKEN',
            'TELEGRAM_CHANNEL_ID',
            'ADMIN_TELEGRAM_ID',
            'DATA_FILE_PATH',
            'APP_TIMEZONE',
            'SUBSCRIPTION_PRICE_STARS',
            'SUBSCRIPTION_DURATION_DAYS',
            'WARNING_DAYS',
            'AUTO_CREATE_INVITE_LINK',
            'POLL_TIMEOUT_SECONDS',
            'SERVICE_CHECK_INTERVAL_MS',
            'SUPPORT_USERNAME',
        }
        self.assertTrue(expected_keys.issubset(keys))
        self.assertIn('-1001234567890', content)
        self.assertIn('Numeric Telegram user id', content)
        self.assertIn('DATA_FILE_PATH=data/db.json', content)

    def test_check_script_exists_if_scripts_dir_present(self):
        scripts_dir = Path('scripts')
        if not scripts_dir.exists():
            self.skipTest('scripts/ directory is not present')

        check_script = scripts_dir / 'check.sh'
        self.assertTrue(check_script.exists())
        content = check_script.read_text(encoding='utf-8-sig')
        self.assertIn('python -m compileall .', content)
        self.assertIn('python -m unittest discover -s tests -p "test_*.py" -v', content)

    def test_backup_script_does_not_reference_absolute_production_path(self):
        path = Path('scripts/backup_db.sh')
        self.assertTrue(path.exists())
        content = path.read_text(encoding='utf-8-sig')

        self.assertIn('data/db.json', content)
        self.assertIn('data/backups', content)
        self.assertNotIn('/opt/private-channel-bot', content)
        self.assertNotIn('C:\\', content)
        self.assertNotIn('D:\\', content)

    def test_scripts_are_posix_friendly_if_present(self):
        scripts_dir = Path('scripts')
        if not scripts_dir.exists():
            self.skipTest('scripts/ directory is not present')

        for path in scripts_dir.iterdir():
            if path.is_file():
                raw = path.read_bytes()
                self.assertNotIn(b'\r\n', raw, msg=f'CRLF found in {path}')
                text = raw.decode('utf-8-sig')
                self.assertNotIn('C:\\', text, msg=f'Windows path found in {path}')
                self.assertNotIn('D:\\', text, msg=f'Windows path found in {path}')

    def test_no_real_tokens_in_docs(self):
        token_pattern = re.compile(r'\b\d{6,12}:[A-Za-z0-9_-]{20,}\b')
        files = [
            Path('.env.example'),
            Path('DEPLOY_UBUNTU.md'),
            Path('RELEASE_CHECKLIST.md'),
            Path('scripts/check.sh'),
            Path('scripts/backup_db.sh'),
            Path('scripts/run_local.sh'),
        ]
        for path in files:
            self.assertTrue(path.exists())
            content = path.read_text(encoding='utf-8-sig')
            self.assertIsNone(token_pattern.search(content), msg=f'Real-looking token found in {path}')


if __name__ == '__main__':
    unittest.main()

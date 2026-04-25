import ast
import unittest
from pathlib import Path

from bot.app import SubscriptionBotApp


class RuntimeShellTests(unittest.TestCase):
    def test_app_shell_public_api_preserved(self):
        expected_methods = {
            'start',
            'stop',
            'handle_update',
            'handle_message',
            'handle_callback_query',
            'handle_admin_command',
            'handle_pre_checkout_query',
            'handle_successful_payment',
            'handle_chat_join_request',
            'run_maintenance_loop',
            'run_subscription_maintenance',
            'render_panel',
            'send_main_menu',
            'send_user_help',
            'send_join_link',
            'send_invoice',
            'approve_pending_request',
            'ensure_invite_link',
            'refresh_invite_link',
            'revoke_user_subscription',
            'get_telegram',
            'get_effective_system_settings',
            'get_effective_admin_credentials',
        }

        for method_name in expected_methods:
            self.assertTrue(hasattr(SubscriptionBotApp, method_name), msg=f'Missing shell method: {method_name}')
            self.assertTrue(callable(getattr(SubscriptionBotApp, method_name)))

    def test_active_runtime_has_no_forbidden_bot_app_imports(self):
        forbidden_files = [
            'bot/dispatcher.py',
            'bot/compat_helpers.py',
            'bot/services/payment_service.py',
            'bot/services/access_service.py',
            'bot/services/maintenance_service.py',
            'bot/services/analytics_service.py',
            'bot/services/plan_service.py',
            'bot/handlers/admin.py',
            'bot/handlers/admin_actions.py',
            'bot/handlers/admin_render.py',
            'bot/handlers/user.py',
            'bot/handlers/user_actions.py',
            'bot/handlers/user_render.py',
            'bot/ui.py',
            'bot/ui_common.py',
            'bot/ui_user.py',
            'bot/ui_admin.py',
        ]

        for relative_path in forbidden_files:
            tree = ast.parse(Path(relative_path).read_text(encoding='utf-8-sig'), filename=relative_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotEqual(alias.name, 'bot.app', msg=f'Forbidden import in {relative_path}')
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, 'bot.app', msg=f'Forbidden import in {relative_path}')
                    if node.module == 'bot':
                        self.assertFalse(any(alias.name == 'app' for alias in node.names), msg=f'Forbidden import in {relative_path}')

    def test_no_windows_absolute_paths_in_active_runtime(self):
        active_runtime_files = [
            'main.py',
            'config.py',
            'store_py.py',
            'telegram_client.py',
            'utils_py.py',
            'bot/app.py',
            'bot/dispatcher.py',
            'bot/compat_helpers.py',
            'bot/fsm.py',
            'bot/ui.py',
            'bot/ui_common.py',
            'bot/ui_user.py',
            'bot/ui_admin.py',
            'bot/services/__init__.py',
            'bot/services/payment_service.py',
            'bot/services/access_service.py',
            'bot/services/maintenance_service.py',
            'bot/services/analytics_service.py',
            'bot/services/plan_service.py',
            'bot/handlers/admin.py',
            'bot/handlers/admin_actions.py',
            'bot/handlers/admin_render.py',
            'bot/handlers/user.py',
            'bot/handlers/user_actions.py',
            'bot/handlers/user_render.py',
        ]

        for relative_path in active_runtime_files:
            source = Path(relative_path).read_text(encoding='utf-8-sig')
            self.assertNotIn('D:\\', source, msg=f'Windows path found in {relative_path}')
            self.assertNotIn('C:\\', source, msg=f'Windows path found in {relative_path}')

    def test_ubuntu_deploy_doc_exists(self):
        path = Path('DEPLOY_UBUNTU.md')
        self.assertTrue(path.exists())

        content = path.read_text(encoding='utf-8-sig')
        required_snippets = [
            'sudo apt install python3 python3-venv python3-pip',
            'python3 -m venv .venv',
            'pip install -r requirements.txt',
            'python -m compileall .',
            'python -m unittest discover -s tests -p "test_*.py" -v',
            'python main.py',
            '/etc/systemd/system/private-channel-bot.service',
            'journalctl -u private-channel-bot -f',
            'cp data/db.json data/db.backup.',
            'Production safety checklist',
        ]
        for snippet in required_snippets:
            self.assertIn(snippet, content)

    def test_requirements_file_exists(self):
        path = Path('requirements.txt')
        self.assertTrue(path.exists())
        self.assertTrue(path.read_text(encoding='utf-8-sig').strip())


if __name__ == '__main__':
    unittest.main()


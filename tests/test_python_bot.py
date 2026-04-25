import ast
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import bot.compat_helpers as compat_helpers
from bot.ui import UIProvider
from config import Config, get_config, validate_config
from store_py import create_store


class RuntimeSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.data_file_path = os.path.join(self.tempdir.name, "db.json")

    def make_config(self):
        return Config(
            bot_token="test-token",
            channel_id="@privatechannel",
            admin_username="admin",
            admin_password="secret",
            admin_telegram_id="",
            subscription_price_stars=250,
            subscription_duration_days=30,
            warning_days=3,
            recurring_payments_enabled=False,
            subscription_name="Test Subscription",
            subscription_description="Test private access",
            support_username="support_manager",
            welcome_text="Добро пожаловать.",
            app_timezone="Europe/Saratov",
            base_url="http://127.0.0.1:3000",
            port=3000,
            auto_create_invite_link=True,
            channel_invite_link="",
            poll_timeout_seconds=1,
            service_check_interval_ms=1000,
            data_file_path=self.data_file_path,
            session_secret="session-secret",
            telegram_api_base_url="https://api.telegram.org",
        )

    @staticmethod
    def collect_callback_data(markup):
        callback_values = []
        for row in markup.get("inline_keyboard", []):
            for button in row:
                if "callback_data" in button:
                    callback_values.append(button["callback_data"])
        return callback_values

    def test_main_imports(self):
        import importlib

        module = importlib.import_module("main")

        self.assertTrue(callable(module.main))

    def test_bot_app_imports(self):
        import importlib

        module = importlib.import_module("bot.app")

        self.assertTrue(hasattr(module, "SubscriptionBotApp"))

    def test_editor_helpers_module_imports(self):
        import importlib

        module = importlib.import_module("bot.compat_helpers")

        self.assertTrue(hasattr(module, "get_admin_view_model"))
        self.assertTrue(hasattr(module, "render_message_template"))
        self.assertTrue(hasattr(module, "configure_channel"))
        self.assertTrue(hasattr(module, "get_dashboard_stats_extended"))

    def test_runtime_has_expected_entrypoints(self):
        from bot.app import SubscriptionBotApp

        store = create_store(self.data_file_path)
        app = SubscriptionBotApp(self.make_config(), store)

        self.assertTrue(callable(app.start))
        self.assertTrue(callable(app.handle_message))
        self.assertTrue(callable(app.handle_callback_query))
        self.assertTrue(callable(app.handle_chat_join_request))
        self.assertTrue(callable(app.run_subscription_maintenance))
        self.assertIsNotNone(app.admin_handler)
        self.assertIsNotNone(app.user_handler)
        self.assertIsNotNone(app.fsm)

    def test_bot_app_public_entrypoints_exist(self):
        from bot.app import SubscriptionBotApp

        expected_methods = {
            "start",
            "stop",
            "handle_message",
            "handle_callback_query",
            "handle_pre_checkout_query",
            "handle_chat_join_request",
            "run_subscription_maintenance",
            "render_panel",
            "send_main_menu",
            "send_join_link",
        }

        for method_name in expected_methods:
            self.assertTrue(hasattr(SubscriptionBotApp, method_name), msg=f"Missing public method: {method_name}")
            self.assertTrue(callable(getattr(SubscriptionBotApp, method_name)))

    def test_bot_app_reexports_compat_helpers(self):
        from bot.app import SubscriptionBotApp

        store = create_store(self.data_file_path)
        app = SubscriptionBotApp(self.make_config(), store)

        with patch.object(compat_helpers, "get_template_context", return_value={"subscriptionUntil": "ok"}) as template_mock:
            self.assertEqual(app.get_template_context(123), {"subscriptionUntil": "ok"})
        template_mock.assert_called_once_with(app, 123)

        with patch.object(compat_helpers, "configure_channel", return_value=None) as configure_mock:
            app.configure_channel("@privatechannel")
        configure_mock.assert_called_once_with(app, "@privatechannel")

        with patch.object(compat_helpers, "get_dashboard_stats_extended", return_value={"totalUsers": 1}) as stats_mock:
            self.assertEqual(app.get_dashboard_stats_extended(), {"totalUsers": 1})
        stats_mock.assert_called_once_with(app)

    def test_main_wires_current_runtime(self):
        import main

        config = self.make_config()
        store = object()
        app_instance = MagicMock()

        with patch.object(main, "load_dotenv") as load_dotenv_mock, \
             patch.object(main, "get_config", return_value=config) as get_config_mock, \
             patch.object(main, "validate_config") as validate_config_mock, \
             patch.object(main, "create_store", return_value=store) as create_store_mock, \
             patch.object(main, "SubscriptionBotApp", return_value=app_instance) as app_cls_mock:
            main.main()

        load_dotenv_mock.assert_called_once_with()
        get_config_mock.assert_called_once_with()
        validate_config_mock.assert_called_once_with(config)
        create_store_mock.assert_called_once_with(config.data_file_path)
        app_cls_mock.assert_called_once_with(config, store)
        app_instance.start.assert_called_once_with()

    def test_config_validation_with_test_env(self):
        env = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_CHANNEL_ID": "@privatechannel",
            "ADMIN_USERNAME": "admin",
            "ADMIN_PASSWORD": "secret",
            "DATA_FILE_PATH": self.data_file_path,
        }

        with patch.dict(os.environ, env, clear=True):
            config = get_config()
            validate_config(config)

        self.assertEqual(config.bot_token, "test-token")
        self.assertEqual(config.channel_id, "@privatechannel")
        self.assertEqual(config.admin_password, "secret")
        self.assertEqual(config.data_file_path, self.data_file_path)

    def test_no_legacy_app_py_imports(self):
        for path in Path("tests").rglob("test_*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = {alias.name for alias in node.names}
                    self.assertNotIn("app_py", imported, msg=f"Legacy import found in {path}")
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, "app_py", msg=f"Legacy import found in {path}")

    def test_legacy_not_imported_by_runtime(self):
        for relative_path in ["main.py", "bot/app.py", "bot/dispatcher.py", "bot/compat_helpers.py", "bot/services/payment_service.py", "bot/services/access_service.py", "bot/services/maintenance_service.py", "bot/handlers/admin.py", "bot/handlers/admin_actions.py", "bot/handlers/admin_render.py", "bot/handlers/user.py", "bot/handlers/user_actions.py", "bot/handlers/user_render.py", "bot/ui.py", "bot/ui_common.py", "bot/ui_user.py", "bot/ui_admin.py"]:
            tree = ast.parse(Path(relative_path).read_text(encoding="utf-8-sig"), filename=relative_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(alias.name.startswith("legacy"), msg=f"Legacy import found in {relative_path}")
                        self.assertNotIn(alias.name, {"app_py", "admin_server_py"}, msg=f"Legacy import found in {relative_path}")
                elif isinstance(node, ast.ImportFrom):
                    module_name = node.module or ""
                    self.assertFalse(module_name.startswith("legacy"), msg=f"Legacy import found in {relative_path}")
                    self.assertNotIn(module_name, {"app_py", "admin_server_py"}, msg=f"Legacy import found in {relative_path}")

    def test_editor_helpers_do_not_import_bot_app(self):
        tree = ast.parse(Path("bot/compat_helpers.py").read_text(encoding="utf-8-sig"), filename="bot/compat_helpers.py")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "bot.app")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "bot.app")

    def test_runtime_still_does_not_import_legacy(self):
        for relative_path in ["main.py", "bot/app.py", "bot/dispatcher.py", "bot/compat_helpers.py", "bot/services/payment_service.py", "bot/services/access_service.py", "bot/services/maintenance_service.py", "bot/handlers/admin.py", "bot/handlers/admin_actions.py", "bot/handlers/admin_render.py", "bot/handlers/user.py", "bot/handlers/user_actions.py", "bot/handlers/user_render.py", "bot/ui.py", "bot/ui_common.py", "bot/ui_user.py", "bot/ui_admin.py"]:
            source = Path(relative_path).read_text(encoding="utf-8-sig")
            self.assertNotIn("legacy.", source, msg=f"Legacy runtime reference found in {relative_path}")
            self.assertNotIn("app_py", source, msg=f"Legacy runtime reference found in {relative_path}")

    def test_runtime_source_files_compile(self):
        files = [
            "main.py",
            "config.py",
            "store_py.py",
            "telegram_client.py",
            "utils_py.py",
            "bot/app.py",
            "bot/dispatcher.py",
            "bot/compat_helpers.py",
            "bot/services/__init__.py",
            "bot/services/payment_service.py",
            "bot/services/access_service.py",
            "bot/services/maintenance_service.py",
            "bot/fsm.py",
            "bot/ui.py",
            "bot/ui_common.py",
            "bot/ui_user.py",
            "bot/ui_admin.py",
            "bot/handlers/admin.py",
            "bot/handlers/admin_actions.py",
            "bot/handlers/admin_render.py",
            "bot/handlers/user.py",
            "bot/handlers/user_actions.py",
            "bot/handlers/user_render.py",
        ]

        for relative_path in files:
            path = Path(relative_path)
            source = path.read_text(encoding="utf-8-sig")
            code = compile(source, str(path), "exec")
            self.assertIsNotNone(code, msg=f"Failed to compile {path}")

    def test_runtime_user_texts_do_not_contain_mojibake_markers(self):
        files = [
            "config.py",
            "store_py.py",
            "bot/app.py",
            "bot/dispatcher.py",
            "bot/compat_helpers.py",
            "bot/services/payment_service.py",
            "bot/services/access_service.py",
            "bot/services/maintenance_service.py",
            "bot/ui.py",
            "bot/ui_common.py",
            "bot/ui_user.py",
            "bot/ui_admin.py",
            "bot/handlers/admin.py",
            "bot/handlers/admin_actions.py",
            "bot/handlers/admin_render.py",
            "bot/handlers/user.py",
            "bot/handlers/user_actions.py",
            "bot/handlers/user_render.py",
        ]
        markers = ("Ð", "Ñ", "Рџ", "рџ", "вќ", "вњ", "вљ", "\ufffd")
        violations = []

        for relative_path in files:
            path = Path(relative_path)
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if any(marker in node.value for marker in markers):
                        value = node.value.replace("\n", "\\n")
                        violations.append(f"{relative_path}:{getattr(node, 'lineno', '?')}: {value[:80]}")

        self.assertFalse(violations, "Found mojibake markers:\n" + "\n".join(violations))

    def test_callback_data_constants_or_buttons_stable(self):
        user_context = {
            "settings": {
                "subscriptionName": "Test Subscription",
                "welcomeText": "Welcome",
                "subscriptionPriceStars": 250,
                "subscriptionDurationDays": 30,
                "supportUsername": "support_manager",
            },
            "user": {"balanceStars": 300},
            "is_active": False,
            "effective_invite_link": "",
            "system": {"appTimezone": "Europe/Saratov"},
            "notice": None,
            "is_admin": True,
        }
        _, user_markup = UIProvider.get_main_menu(user_context)
        user_callbacks = set(self.collect_callback_data(user_markup))
        self.assertTrue({"buy", "join", "user:help", "buy_balance", "admin:menu"}.issubset(user_callbacks))

        admin_stats = {
            "totalUsers": 1,
            "activeSubscriptions": 1,
            "channelMembers": 1,
            "pendingJoinRequests": 0,
            "revenueStars": 10,
            "revenueMonth": 10,
        }
        admin_system = {"channelId": "@privatechannel", "autoCreateInviteLink": True}
        _, admin_main_markup = UIProvider.get_admin_main(admin_stats, admin_system, "")
        admin_main_callbacks = set(self.collect_callback_data(admin_main_markup))
        self.assertTrue({
            "admin:users:0",
            "admin:stats",
            "admin:settings",
            "admin:broadcast:menu",
            "admin:refresh_invite",
            "panel:main",
        }.issubset(admin_main_callbacks))

        admin_settings = {
            "subscriptionPriceStars": 250,
            "subscriptionDurationDays": 30,
            "warningDays": 3,
            "supportUsername": "support_manager",
        }
        _, admin_settings_markup = UIProvider.get_admin_settings(admin_settings, admin_system)
        admin_settings_callbacks = set(self.collect_callback_data(admin_settings_markup))
        self.assertTrue({
            "admin:input:price",
            "admin:input:days",
            "admin:input:warning",
            "admin:toggle:recurring",
            "admin:toggle:autoinvite",
            "admin:input:channel",
            "admin:input:support",
            "admin:templates:menu",
            "admin:menu",
        }.issubset(admin_settings_callbacks))

    def test_commands_still_documented_consistently(self):
        readme = Path("README.md").read_text(encoding="utf-8-sig")
        supported_direct_commands = {
            "/admin",
            "/admin_login <username> <password>",
            "/admin_logout",
            "/admin_stats",
            "/admin_settings",
            "/admin_users",
            "/admin_help",
            "/admin_refresh_invite",
            "/admin_broadcast",
            "/admin_payment_diag <user_id>",
            "/admin_recover_payment <user_id> <days> <reason>",
            "/admin_payment_anomalies",
        }
        documented_but_not_direct = {
            "/admin_set",
            "/admin_user",
            "/admin_create_user",
            "/admin_grant",
            "/admin_revoke",
            "/admin_balance",
            "/admin_approve",
            "/admin_message",
            "/admin_note",
            "/admin_setup_channel",
        }

        for command in supported_direct_commands:
            self.assertIn(command, readme)

        self.assertIn("не реализованы как прямые slash-команды", readme)
        for command in documented_but_not_direct:
            self.assertIn(command, readme)

    def test_docs_and_package_do_not_point_to_legacy_runtime(self):
        readme = Path("README.md").read_text(encoding="utf-8-sig")
        package = json.loads(Path("package.json").read_text(encoding="utf-8-sig"))
        legacy_readme = Path("legacy/README_LEGACY.md")

        self.assertIn("python main.py", readme)
        self.assertNotIn("app_py", readme)
        self.assertIn("legacy/README_LEGACY.md", readme)
        self.assertTrue(legacy_readme.exists())
        self.assertNotIn("index.js", package.get("scripts", {}).get("start", ""))
        self.assertNotIn("index.js", package.get("scripts", {}).get("check", ""))
        self.assertNotEqual(package.get("main"), "index.js")


if __name__ == "__main__":
    unittest.main()








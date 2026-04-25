import ast
import tempfile
import unittest
from pathlib import Path

from bot.app import SubscriptionBotApp
from bot.dispatcher import dispatch_admin_command
from bot.ui import UIProvider
from config import Config
from fakes import FakeTelegramClient
from store_py import create_store


class AdminHandlerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.data_file_path = self.tempdir.name + "\\db.json"

    def make_config(self, admin_telegram_id="999"):
        return Config(
            bot_token="test-token",
            channel_id="@privatechannel",
            admin_username="admin",
            admin_password="secret",
            admin_telegram_id=admin_telegram_id,
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

    def make_app(self, fake_client=None, admin_telegram_id="999"):
        config = self.make_config(admin_telegram_id=admin_telegram_id)
        store = create_store(config.data_file_path)
        app = SubscriptionBotApp(config, store)
        app.telegram = fake_client or FakeTelegramClient()
        app.current_bot_token = config.bot_token
        app.current_api_base_url = config.telegram_api_base_url
        app._bootstrap()
        return app

    @staticmethod
    def _callback_values(markup):
        values = []
        for row in markup.get("inline_keyboard", []):
            for button in row:
                if "callback_data" in button:
                    values.append(button["callback_data"])
        return values

    def test_admin_handlers_import_without_bot_app_cycle(self):
        for relative_path in [
            "bot/handlers/admin.py",
            "bot/handlers/admin_actions.py",
            "bot/handlers/admin_render.py",
        ]:
            tree = ast.parse(Path(relative_path).read_text(encoding="utf-8-sig"), filename=relative_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotEqual(alias.name, "bot.app")
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, "bot.app")

    def test_admin_direct_commands_preserved(self):
        app = self.make_app()
        expected = {
            "/admin",
            "/admin_channel_check",
            "/admin_health",
            "/admin_login",
            "/admin_logout",
            "/admin_stats",
            "/admin_revenue",
            "/admin_activity",
            "/admin_payment_diag",
            "/admin_recover_payment",
            "/admin_payment_anomalies",
        }
        self.assertTrue(expected.issubset(app.ADMIN_COMMANDS))

    def test_admin_payment_diag_command_still_works(self):
        admin_client = FakeTelegramClient()
        admin_app = self.make_app(fake_client=admin_client)
        admin_app.store.ensure_user({"id": 120, "first_name": "Diag", "username": "diag"})

        dispatch_admin_command(admin_app, {"from": {"id": 999}}, "/admin_payment_diag", "120")

        self.assertEqual(len(admin_client.get_calls("send_message")), 1)
        self.assertIn("Диагностика платежей", admin_client.get_calls("send_message")[0]["text"])

        user_client = FakeTelegramClient()
        user_app = self.make_app(fake_client=user_client)
        dispatch_admin_command(user_app, {"from": {"id": 121}}, "/admin_payment_diag", "120")
        self.assertIn("/admin_login", user_client.get_calls("send_message")[0]["text"])

    def test_admin_recover_payment_command_still_works(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 123, "first_name": "Recover", "username": "recover"})
        before = dict(app.store.get_user(123))

        dispatch_admin_command(
            app,
            {"from": {"id": 999}},
            "/admin_recover_payment",
            "123 15 manual_verification",
        )

        user = app.store.get_user(123)
        self.assertGreater(user["subscriptionUntil"], before.get("subscriptionUntil") or 0)
        self.assertEqual(user["totalPaymentsCount"], before.get("totalPaymentsCount", 0))
        self.assertEqual(user["totalSpentStars"], before.get("totalSpentStars", 0))
        self.assertEqual(app.store.get_payments(), [])
        audit = app.store.get_audit_log()[-1]
        self.assertEqual(audit["type"], "manual_payment_recovery")

    def test_admin_payment_anomalies_command_still_works(self):
        admin_client = FakeTelegramClient()
        admin_app = self.make_app(fake_client=admin_client)
        admin_app.store.ensure_user({"id": 124, "first_name": "Suspicious", "username": "sus"})
        admin_app.store.update_user_fields(124, {"totalPaymentsCount": 2, "totalSpentStars": 500})

        dispatch_admin_command(admin_app, {"from": {"id": 999}}, "/admin_payment_anomalies", "")

        self.assertEqual(len(admin_client.get_calls("send_message")), 1)
        self.assertIn("/admin_payment_diag 124", admin_client.get_calls("send_message")[0]["text"])

        user_client = FakeTelegramClient()
        user_app = self.make_app(fake_client=user_client)
        dispatch_admin_command(user_app, {"from": {"id": 1221}}, "/admin_payment_anomalies", "")
        self.assertIn("/admin_login", user_client.get_calls("send_message")[0]["text"])

    def test_admin_callbacks_preserve_known_callback_data(self):
        main_markup = UIProvider.get_admin_main(
            {"totalUsers": 1, "activeSubscriptions": 1, "channelMembers": 1, "pendingJoinRequests": 0, "revenueStars": 0, "revenueMonth": 0},
            {"channelId": "@privatechannel"},
            "",
            None,
        )[1]
        settings_markup = UIProvider.get_admin_settings(
            {"subscriptionPriceStars": 250, "subscriptionDurationDays": 30, "warningDays": 3, "supportUsername": "support"},
            {"autoCreateInviteLink": True},
            None,
        )[1]
        user_markup = UIProvider.get_admin_user_details(
            {"id": 1, "balanceStars": 0, "subscriptionUntil": 0, "channelMemberStatus": "left", "notes": "", "first_name": "Test"},
            {"appTimezone": "Europe/Saratov"},
            None,
        )[1]

        callbacks = set(self._callback_values(main_markup) + self._callback_values(settings_markup) + self._callback_values(user_markup))
        expected = {
            "admin:menu",
            "admin:payment_anomalies",
            "admin:users:0",
            "admin:settings",
            "admin:stats",
            "admin:refresh_invite",
            "admin:input:price",
            "admin:toggle:recurring",
            "admin:approve:1",
            "admin:revoke:1",
        }
        self.assertTrue(expected.issubset(callbacks))

    def test_admin_unknown_callback_does_not_crash(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)

        app.admin_handler.handle_callback(
            {
                "id": "cb-unknown",
                "from": {"id": 999},
                "data": "admin:unknown:noop",
                "message": {"message_id": 1},
            }
        )

        answer_calls = fake_client.get_calls("answer_callback_query")
        self.assertEqual(len(answer_calls), 1)
        self.assertEqual(answer_calls[0]["callback_query_id"], "cb-unknown")

    def test_admin_command_argument_errors_preserved(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 126, "first_name": "Args", "username": "args"})
        before = app.store.get_state()

        dispatch_admin_command(app, {"from": {"id": 999}}, "/admin_payment_anomalies", "oops")
        dispatch_admin_command(app, {"from": {"id": 999}}, "/admin_recover_payment", "126 nope reason")

        messages = [call["text"] for call in fake_client.get_calls("send_message")]
        self.assertTrue(any("/admin_payment_anomalies [LIMIT]" in text for text in messages))
        self.assertTrue(any("USER_ID и DAYS должны быть числами." in text for text in messages))
        self.assertEqual(before["payments"], app.store.get_state()["payments"])
        self.assertEqual(before["auditLog"], app.store.get_state()["auditLog"])


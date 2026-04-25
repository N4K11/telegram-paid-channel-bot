import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.app import SubscriptionBotApp
from bot.services import maintenance_service
from config import Config
from store_py import create_store
from fakes import FakeTelegramClient


DAY_MS = 24 * 3600 * 1000


class MaintenanceServiceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.data_file_path = str(Path(self.tempdir.name) / "db.json")

    def make_config(self):
        return Config(
            bot_token="test-token",
            channel_id="@privatechannel",
            admin_username="admin",
            admin_password="secret",
            admin_telegram_id="999",
            subscription_price_stars=250,
            subscription_duration_days=30,
            warning_days=3,
            recurring_payments_enabled=False,
            subscription_name="Test Subscription",
            subscription_description="Test private access",
            support_username="support_manager",
            welcome_text="Welcome",
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

    def make_app(self, fake_client=None):
        config = self.make_config()
        store = create_store(config.data_file_path)
        app = SubscriptionBotApp(config, store)
        app.telegram = fake_client or FakeTelegramClient()
        app.current_bot_token = config.bot_token
        app.current_api_base_url = config.telegram_api_base_url
        return app

    def test_maintenance_service_module_imports_without_bot_app_cycle(self):
        module = __import__("bot.services.maintenance_service", fromlist=["maintenance_service"])
        self.assertIsNotNone(module)

        tree = ast.parse(Path("bot/services/maintenance_service.py").read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "bot.app")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "bot.app")

    def test_should_send_warning_inside_window(self):
        fixed_now = 1_700_000_000_000
        settings = {"warningDays": 3}
        user = {"subscriptionUntil": fixed_now + 2 * DAY_MS, "lastWarningAt": None}

        self.assertTrue(maintenance_service.should_send_warning(user, settings, fixed_now))

    def test_should_not_send_warning_twice(self):
        fixed_now = 1_700_000_000_000
        settings = {"warningDays": 3}
        user = {"subscriptionUntil": fixed_now + 2 * DAY_MS, "lastWarningAt": fixed_now}

        self.assertFalse(maintenance_service.should_send_warning(user, settings, fixed_now))

    def test_warning_notification_marks_sent(self):
        fixed_now = 1_700_000_000_000
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 301, "first_name": "Warn", "username": "warn"})
        app.store.update_user_fields(301, {"subscriptionUntil": fixed_now + 2 * DAY_MS, "lastWarningAt": None})

        maintenance_service.process_maintenance_user(
            app,
            app.store.get_user(301),
            app.store.get_settings(),
            now_ms=fixed_now,
        )

        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 1)
        self.assertIn("скоро закончится", send_calls[0]["text"])
        self.assertIsNotNone(app.store.get_user(301)["lastWarningAt"])

    def test_expired_subscription_revokes_access(self):
        fixed_now = 1_700_000_000_000
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 302, "first_name": "Expired", "username": "expired"})
        app.store.update_user_fields(302, {"subscriptionUntil": fixed_now - 1, "lastAccessRevokedAt": None})

        with patch.object(app, "revoke_user_subscription", wraps=app.revoke_user_subscription) as revoke_mock:
            maintenance_service.process_maintenance_user(
                app,
                app.store.get_user(302),
                app.store.get_settings(),
                now_ms=fixed_now,
            )

        revoke_mock.assert_called_once_with(302, "expired")
        self.assertIsNotNone(app.store.get_user(302)["lastAccessRevokedAt"])
        send_calls = fake_client.get_calls("send_message")
        self.assertTrue(any("истекла" in call["text"] for call in send_calls))

    def test_expired_revoke_error_does_not_stop_other_users(self):
        fixed_now = 1_700_000_000_000
        app = self.make_app(fake_client=FakeTelegramClient())
        app.store.ensure_user({"id": 303, "first_name": "First", "username": "first"})
        app.store.ensure_user({"id": 304, "first_name": "Second", "username": "second"})
        app.store.update_user_fields(303, {"subscriptionUntil": fixed_now - 1, "lastAccessRevokedAt": None})
        app.store.update_user_fields(304, {"subscriptionUntil": fixed_now - 1, "lastAccessRevokedAt": None})

        original_revoke = app.revoke_user_subscription

        def revoke_side_effect(user_id, reason):
            if user_id == 303:
                raise RuntimeError("revoke failed")
            return original_revoke(user_id, reason)

        with patch.object(app, "revoke_user_subscription", side_effect=revoke_side_effect), \
             patch.object(app, "_log_error") as log_mock:
            maintenance_service.run_subscription_maintenance(app, now_ms=fixed_now)

        self.assertIsNone(app.store.get_user(303)["lastAccessRevokedAt"])
        self.assertIsNotNone(app.store.get_user(304)["lastAccessRevokedAt"])
        self.assertTrue(any("Maintenance user error for 303" in str(call.args[0]) for call in log_mock.call_args_list))

    def test_stale_pending_request_declined(self):
        fixed_now = 1_700_000_000_000
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 305, "first_name": "OldPending", "username": "oldpending"})
        app.store.update_user_fields(305, {"subscriptionUntil": fixed_now + DAY_MS})
        app.store.set_user_pending_join_request(305, {"chatId": -100123456, "createdAt": fixed_now - app.JOIN_REQUEST_TTL_MS - 1})

        maintenance_service.process_maintenance_user(
            app,
            app.store.get_user(305),
            app.store.get_settings(),
            now_ms=fixed_now,
        )

        decline_calls = fake_client.get_calls("decline_chat_join_request")
        self.assertEqual(len(decline_calls), 1)
        self.assertIsNone(app.store.get_user(305)["pendingJoinRequest"])

    def test_fresh_pending_request_not_declined(self):
        fixed_now = 1_700_000_000_000
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 306, "first_name": "FreshPending", "username": "freshpending"})
        app.store.update_user_fields(306, {"subscriptionUntil": fixed_now + DAY_MS})
        app.store.set_user_pending_join_request(306, {"chatId": -100123456, "createdAt": fixed_now - 1000})

        maintenance_service.process_maintenance_user(
            app,
            app.store.get_user(306),
            app.store.get_settings(),
            now_ms=fixed_now,
        )

        self.assertEqual(fake_client.get_calls("decline_chat_join_request"), [])
        self.assertIsNotNone(app.store.get_user(306)["pendingJoinRequest"])

    def test_maintenance_does_not_touch_active_far_from_expiry(self):
        fixed_now = 1_700_000_000_000
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 307, "first_name": "Far", "username": "far"})
        app.store.update_user_fields(307, {"subscriptionUntil": fixed_now + 10 * DAY_MS, "lastWarningAt": None, "lastAccessRevokedAt": None})

        maintenance_service.process_maintenance_user(
            app,
            app.store.get_user(307),
            app.store.get_settings(),
            now_ms=fixed_now,
        )

        self.assertEqual(fake_client.get_calls("send_message"), [])
        self.assertEqual(fake_client.get_calls("ban_chat_member"), [])
        self.assertEqual(fake_client.get_calls("decline_chat_join_request"), [])
        user = app.store.get_user(307)
        self.assertIsNone(user["lastWarningAt"])
        self.assertIsNone(user["lastAccessRevokedAt"])

    def test_bot_app_wrappers_delegate_to_maintenance_service(self):
        app = self.make_app()
        user = {"id": 1, "subscriptionUntil": 1}

        with patch.object(maintenance_service, "process_maintenance_user", return_value=None) as process_mock:
            self.assertIsNone(app._process_maintenance_user(user, 123, 456))
        process_mock.assert_called_once()
        args, kwargs = process_mock.call_args
        self.assertEqual(args[0], app)
        self.assertEqual(args[1], user)
        self.assertEqual(kwargs["now_ms"], 123)
        self.assertEqual(kwargs["warning_ms"], 456)

        with patch.object(maintenance_service, "run_subscription_maintenance", return_value=None) as run_mock:
            self.assertIsNone(app.run_subscription_maintenance())
        run_mock.assert_called_once_with(app)


if __name__ == "__main__":
    unittest.main()

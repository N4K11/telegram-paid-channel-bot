import ast
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.app import SubscriptionBotApp
from bot.services import health_service
from config import Config
from fakes import FakeTelegramClient
from store_py import create_store


class HealthServiceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.data_file_path = self.tempdir.name + "\\db.json"

    def make_config(self, channel_id="@privatechannel"):
        return Config(
            bot_token="test-token",
            channel_id=channel_id,
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

    def make_app(self, fake_client=None, channel_id="@privatechannel"):
        config = self.make_config(channel_id=channel_id)
        store = create_store(config.data_file_path)
        app = SubscriptionBotApp(config, store)
        app.telegram = fake_client or FakeTelegramClient()
        app.current_bot_token = config.bot_token
        app.current_api_base_url = config.telegram_api_base_url
        app._bootstrap()
        return app

    def test_health_service_module_imports_without_bot_app_cycle(self):
        tree = ast.parse(
            Path("bot/services/health_service.py").read_text(encoding="utf-8-sig"),
            filename="bot/services/health_service.py",
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "bot.app")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "bot.app")

    def test_health_read_only(self):
        app = self.make_app()
        now_ms = int(time.time() * 1000)
        app.store.ensure_user({"id": 101, "first_name": "Active", "username": "active"})
        app.store.ensure_user({"id": 102, "first_name": "Expired", "username": "expired"})
        app.store.update_user_fields(
            101,
            {"subscriptionUntil": now_ms + 24 * 3600 * 1000},
        )
        app.store.update_user_fields(
            102,
            {
                "subscriptionUntil": now_ms - 1000,
                "pendingJoinRequest": {"chatId": -100123, "createdAt": now_ms - 2000},
            },
        )
        app.store.set_last_update_id(55)
        app.last_maintenance_run_at = now_ms - 5000
        before = app.store.get_state()

        status = health_service.get_health_status(app)
        text = health_service.format_health_status(status, app.config.app_timezone)

        self.assertEqual(before, app.store.get_state())
        self.assertEqual(status["lastUpdateId"], 55)
        self.assertEqual(status["activeUsers"], 1)
        self.assertEqual(status["expiredUsers"], 1)
        self.assertEqual(status["pendingJoinRequests"], 1)
        self.assertIn("Bot healthcheck", text)
        self.assertIn("Last update id: <b>55</b>", text)
        self.assertIn("Active users: <b>1</b>", text)

    def test_health_store_writable_ok(self):
        app = self.make_app()

        status = health_service.get_health_status(app)

        self.assertTrue(status["storeWritable"])
        self.assertEqual(status["storeWritableError"], "")

    def test_health_store_writable_fail(self):
        app = self.make_app()

        with patch.object(
            health_service,
            "_check_store_writable",
            return_value={"ok": False, "error": "permission denied"},
        ):
            status = health_service.get_health_status(app)
            text = health_service.format_health_status(status, app.config.app_timezone)

        self.assertFalse(status["storeWritable"])
        self.assertEqual(status["storeWritableError"], "permission denied")
        self.assertIn("Store writable: <b>no</b>", text)
        self.assertIn("permission denied", text)

    def test_health_without_channel_config(self):
        app = self.make_app(channel_id="")

        status = health_service.get_health_status(app)

        self.assertFalse(status["channelConfigured"])
        self.assertEqual(status["channelId"], "")


if __name__ == "__main__":
    unittest.main()

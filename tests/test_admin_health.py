import tempfile
import time
import unittest

from bot.app import SubscriptionBotApp
from config import Config
from fakes import FakeTelegramClient
from store_py import create_store


class AdminHealthTests(unittest.TestCase):
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

    def test_admin_health_requires_admin(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client, admin_telegram_id="999")

        app.handle_message(
            {
                "message_id": 1,
                "text": "/admin_health",
                "from": {"id": 123, "first_name": "User", "username": "user"},
            }
        )

        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 1)
        self.assertIn("/admin_login", send_calls[0]["text"])

    def test_admin_health_output_does_not_expose_token(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client, admin_telegram_id="999")
        app.last_runtime_error = {
            "context": "Telegram API error at getMe",
            "error": "Forbidden: bad token 123456789:ABCDEF_token_hidden_example",
            "loggedAt": int(time.time() * 1000),
        }

        app.handle_message(
            {
                "message_id": 2,
                "text": "/admin_health",
                "from": {"id": 999, "first_name": "Admin", "username": "boss"},
            }
        )

        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 1)
        text = send_calls[0]["text"]
        self.assertIn("Bot healthcheck", text)
        self.assertIn("Last runtime/API error", text)
        self.assertNotIn("123456789:ABCDEF_token_hidden_example", text)
        self.assertIn("<redacted-token>", text)


if __name__ == "__main__":
    unittest.main()

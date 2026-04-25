import tempfile
import unittest

from bot.app import SubscriptionBotApp
from config import Config
from fakes import FakeTelegramClient
from store_py import create_store
from utils_py import parse_datetime_local_value


class AdminAnalyticsTests(unittest.TestCase):
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

    def ensure_payment(self, app, user_id, charge_id, amount, paid_at):
        app.store.ensure_user({"id": user_id, "first_name": f"User{user_id}", "username": f"user{user_id}"})
        app.store.record_payment(
            {
                "telegramPaymentChargeId": charge_id,
                "userId": user_id,
                "totalAmount": amount,
                "paidAt": paid_at,
                "invoicePayload": f"subscription:{user_id}",
                "currency": "XTR",
            }
        )

    def test_admin_analytics_requires_admin(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client, admin_telegram_id="999")

        app.handle_message(
            {
                "message_id": 1,
                "text": "/admin_revenue",
                "from": {"id": 123, "first_name": "User", "username": "user"},
            }
        )

        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 1)
        self.assertIn("/admin_login", send_calls[0]["text"])

    def test_admin_stats_command_still_works(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client, admin_telegram_id="999")
        now_ms = parse_datetime_local_value("2026-04-08T12:00", app.config.app_timezone)
        app.store.ensure_user({"id": 200, "first_name": "Active", "username": "active"})
        app.store.update_user_fields(200, {"subscriptionUntil": now_ms + (5 * 24 * 3600 * 1000)})
        self.ensure_payment(app, 200, "charge_stats", 250, now_ms - 1000)

        app.handle_message(
            {
                "message_id": 2,
                "text": "/admin_stats",
                "from": {"id": 999, "first_name": "Admin", "username": "boss"},
            }
        )

        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 1)
        text = send_calls[0]["text"]
        self.assertIn("Расширенная статистика", text)
        self.assertIn("Доход за день", text)
        self.assertIn("Доход за неделю", text)
        self.assertIn("Топ по оплатам", text)

    def test_admin_revenue_command_outputs_periods(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client, admin_telegram_id="999")
        now_ms = parse_datetime_local_value("2026-04-08T12:00", app.config.app_timezone)
        self.ensure_payment(app, 201, "charge_revenue_1", 100, parse_datetime_local_value("2026-04-08T09:00", app.config.app_timezone))
        self.ensure_payment(app, 202, "charge_revenue_2", 200, parse_datetime_local_value("2026-04-07T09:00", app.config.app_timezone))

        app.handle_message(
            {
                "message_id": 3,
                "text": "/admin_revenue",
                "from": {"id": 999, "first_name": "Admin", "username": "boss"},
            }
        )

        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 1)
        text = send_calls[0]["text"]
        self.assertIn("Доход и платежи", text)
        self.assertIn("За день", text)
        self.assertIn("За неделю", text)
        self.assertIn("За 30 дней", text)
        self.assertIn("Топ пользователей по оплатам", text)

    def test_admin_activity_command_outputs_counts(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client, admin_telegram_id="999")
        now_ms = parse_datetime_local_value("2026-04-08T12:00", app.config.app_timezone)
        app.store.ensure_user({"id": 203, "first_name": "Active", "username": "active"})
        app.store.ensure_user({"id": 204, "first_name": "Expired", "username": "expired"})
        app.store.update_user_fields(203, {"subscriptionUntil": now_ms + (2 * 24 * 3600 * 1000)})
        app.store.update_user_fields(204, {"subscriptionUntil": now_ms - 1000})
        app.store.set_user_pending_join_request(203, {"chatId": -100123, "createdAt": now_ms})
        self.ensure_payment(app, 203, "charge_activity", 250, now_ms - 1000)

        app.handle_message(
            {
                "message_id": 4,
                "text": "/admin_activity",
                "from": {"id": 999, "first_name": "Admin", "username": "boss"},
            }
        )

        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 1)
        text = send_calls[0]["text"]
        self.assertIn("Активность пользователей", text)
        self.assertIn("Активных подписок", text)
        self.assertIn("Истекших", text)
        self.assertIn("Ожидают вход", text)
        self.assertIn("Последний платёж", text)


if __name__ == "__main__":
    unittest.main()

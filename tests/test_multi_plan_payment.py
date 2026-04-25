import tempfile
import time
import unittest

from bot.app import SubscriptionBotApp
from bot.ui import UIProvider
from config import Config
from fakes import FakeTelegramClient
from store_py import create_store


DAY_MS = 24 * 60 * 60 * 1000


class MultiPlanPaymentTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.data_file_path = self.tempdir.name + "\\db.json"

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

    def make_app(self, fake_client=None):
        config = self.make_config()
        store = create_store(config.data_file_path)
        app = SubscriptionBotApp(config, store)
        app.telegram = fake_client or FakeTelegramClient()
        app.current_bot_token = config.bot_token
        app.current_api_base_url = config.telegram_api_base_url
        app._bootstrap()
        app.store.update_settings(
            {
                "plans": [
                    {"id": "day", "title": "1 день", "priceStars": 20, "durationDays": 1, "enabled": True},
                    {"id": "week", "title": "7 дней", "priceStars": 70, "durationDays": 7, "enabled": True},
                    {"id": "month", "title": "30 дней", "priceStars": 250, "durationDays": 30, "enabled": True},
                ]
            }
        )
        return app

    @staticmethod
    def _callback_values(markup):
        values = []
        for row in markup.get("inline_keyboard", []):
            for button in row:
                if "callback_data" in button:
                    values.append(button["callback_data"])
        return values

    def test_buy_callback_opens_plan_picker_when_multiple_plans_enabled(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 301, "first_name": "Buyer", "username": "buyer"})

        app.user_handler.handle_callback(
            {
                "id": "cb-buy-picker",
                "from": {"id": 301},
                "data": "buy",
                "message": {"message_id": 1},
            }
        )

        edit_calls = fake_client.get_calls("edit_message_text")
        self.assertEqual(len(edit_calls), 1)
        self.assertIn("Выберите тариф", edit_calls[0]["text"])
        callbacks = self._callback_values(edit_calls[0]["extra"]["reply_markup"])
        self.assertEqual(callbacks, ["buy:plan:day", "buy:plan:week", "buy:plan:month", "panel:main"])
        self.assertEqual(len(fake_client.get_calls("send_invoice")), 0)

    def test_buy_plan_callback_sends_invoice_with_plan_payload_and_price(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 302, "first_name": "Buyer", "username": "buyer"})

        app.user_handler.handle_callback(
            {
                "id": "cb-buy-week",
                "from": {"id": 302},
                "data": "buy:plan:week",
                "message": {"message_id": 2},
            }
        )

        invoice_calls = fake_client.get_calls("send_invoice")
        self.assertEqual(len(invoice_calls), 1)
        params = invoice_calls[0]["params"]
        self.assertEqual(params["payload"], "subscription:302:week")
        self.assertEqual(params["prices"][0]["amount"], 70)
        self.assertEqual(params["prices"][0]["label"], "7 дней")

    def test_disabled_plan_not_sold(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 303, "first_name": "Buyer", "username": "buyer"})
        app.store.update_settings(
            {
                "plans": [
                    {"id": "day", "title": "1 день", "priceStars": 20, "durationDays": 1, "enabled": True},
                    {"id": "week", "title": "7 дней", "priceStars": 70, "durationDays": 7, "enabled": False},
                ]
            }
        )

        app.user_handler.handle_callback(
            {
                "id": "cb-buy-disabled",
                "from": {"id": 303},
                "data": "buy:plan:week",
                "message": {"message_id": 3},
            }
        )

        self.assertEqual(len(fake_client.get_calls("send_invoice")), 0)
        edit_calls = fake_client.get_calls("edit_message_text")
        self.assertEqual(len(edit_calls), 1)
        self.assertIn("Тариф недоступен", edit_calls[0]["text"])

    def test_new_payload_uses_selected_plan_duration(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 304, "first_name": "Paid", "username": "paid"})
        started_at = int(time.time() * 1000)

        app.handle_message(
            {
                "message_id": 4,
                "from": {"id": 304, "first_name": "Paid", "username": "paid"},
                "successful_payment": {
                    "currency": "XTR",
                    "total_amount": 70,
                    "telegram_payment_charge_id": "charge_week_304",
                    "invoice_payload": "subscription:304:week",
                },
            }
        )

        user = app.store.get_user(304)
        self.assertTrue(app.store.is_subscription_active(304))
        self.assertGreaterEqual(user["subscriptionUntil"] - started_at, 7 * DAY_MS - 60_000)
        self.assertLessEqual(user["subscriptionUntil"] - started_at, 7 * DAY_MS + 300_000)

    def test_duplicate_multi_plan_payment_does_not_extend_twice(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 305, "first_name": "Paid", "username": "paid"})
        message = {
            "message_id": 5,
            "from": {"id": 305, "first_name": "Paid", "username": "paid"},
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 70,
                "telegram_payment_charge_id": "charge_week_305",
                "invoice_payload": "subscription:305:week",
            },
        }

        app.handle_message(message)
        first_until = app.store.get_user(305)["subscriptionUntil"]

        app.handle_message(message)
        second_until = app.store.get_user(305)["subscriptionUntil"]

        self.assertEqual(first_until, second_until)
        self.assertEqual(app.store.get_user(305)["totalPaymentsCount"], 1)

    def test_old_payload_still_works_with_fallback_settings(self):
        fake_client = FakeTelegramClient()
        config = self.make_config()
        store = create_store(config.data_file_path)
        app = SubscriptionBotApp(config, store)
        app.telegram = fake_client
        app.current_bot_token = config.bot_token
        app.current_api_base_url = config.telegram_api_base_url
        app._bootstrap()
        app.store.ensure_user({"id": 306, "first_name": "Legacy", "username": "legacy"})
        started_at = int(time.time() * 1000)

        app.handle_message(
            {
                "message_id": 6,
                "from": {"id": 306, "first_name": "Legacy", "username": "legacy"},
                "successful_payment": {
                    "currency": "XTR",
                    "total_amount": 250,
                    "telegram_payment_charge_id": "charge_legacy_306",
                    "invoice_payload": "subscription:306",
                },
            }
        )

        user = app.store.get_user(306)
        self.assertTrue(app.store.is_subscription_active(306))
        self.assertGreaterEqual(user["subscriptionUntil"] - started_at, 30 * DAY_MS - 60_000)

    def test_buy_balance_plan_uses_selected_price_and_duration(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 307, "first_name": "Balance", "username": "balance"})
        app.store.adjust_balance(307, 100, reason="test_topup")
        started_at = int(time.time() * 1000)

        app.user_handler.handle_callback(
            {
                "id": "cb-buy-balance",
                "from": {"id": 307},
                "data": "buy_balance:plan:week",
                "message": {"message_id": 7},
            }
        )

        user = app.store.get_user(307)
        self.assertEqual(user["balanceStars"], 30)
        self.assertGreaterEqual(user["subscriptionUntil"] - started_at, 7 * DAY_MS - 60_000)

    def test_ui_shows_plans_in_config_order(self):
        _, text_markup = UIProvider.get_plan_picker(
            {
                "subscriptionName": "Test Subscription",
                "subscriptionPriceStars": 250,
                "subscriptionDurationDays": 30,
                "plans": [
                    {"id": "day", "title": "1 день", "priceStars": 20, "durationDays": 1, "enabled": True},
                    {"id": "week", "title": "7 дней", "priceStars": 70, "durationDays": 7, "enabled": True},
                    {"id": "month", "title": "30 дней", "priceStars": 250, "durationDays": 30, "enabled": True},
                ],
            },
            [
                {"id": "day", "title": "1 день", "priceStars": 20, "durationDays": 1, "enabled": True, "isLifetime": False},
                {"id": "week", "title": "7 дней", "priceStars": 70, "durationDays": 7, "enabled": True, "isLifetime": False},
                {"id": "month", "title": "30 дней", "priceStars": 250, "durationDays": 30, "enabled": True, "isLifetime": False},
            ],
        )

        callbacks = self._callback_values(text_markup)
        self.assertEqual(callbacks, ["buy:plan:day", "buy:plan:week", "buy:plan:month", "panel:main"])


if __name__ == "__main__":
    unittest.main()
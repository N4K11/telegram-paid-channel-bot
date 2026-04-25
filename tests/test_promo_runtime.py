import tempfile
import unittest

from bot.app import SubscriptionBotApp
from config import Config
from fakes import FakeTelegramClient
from store_py import create_store


class PromoRuntimeTests(unittest.TestCase):
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

    def test_admin_promo_commands_require_admin(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client, admin_telegram_id="999")

        app.handle_message(
            {
                "message_id": 1,
                "text": "/admin_promo_create SAVE20 discount_percent 20 5",
                "from": {"id": 123, "first_name": "User", "username": "user"},
            }
        )

        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 1)
        self.assertIn("/admin_login", send_calls[0]["text"])
        self.assertIsNone(app.store.get_promo_code("SAVE20"))

    def test_admin_promo_create_stats_disable_flow(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client, admin_telegram_id="999")

        app.handle_message(
            {
                "message_id": 2,
                "text": "/admin_promo_create SAVE20 discount_percent 20 5",
                "from": {"id": 999, "first_name": "Admin", "username": "boss"},
            }
        )
        self.assertIsNotNone(app.store.get_promo_code("SAVE20"))

        app.handle_message(
            {
                "message_id": 3,
                "text": "/admin_promo_stats SAVE20",
                "from": {"id": 999, "first_name": "Admin", "username": "boss"},
            }
        )

        app.handle_message(
            {
                "message_id": 4,
                "text": "/admin_promo_disable SAVE20",
                "from": {"id": 999, "first_name": "Admin", "username": "boss"},
            }
        )

        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 3)
        self.assertIn("SAVE20", send_calls[0]["text"])
        self.assertIn("Promo code", send_calls[1]["text"])
        self.assertIn("SAVE20", send_calls[1]["text"])
        self.assertIn("отключён", send_calls[2]["text"])
        self.assertFalse(app.store.get_promo_code("SAVE20")["enabled"])

    def test_promo_command_free_days_grants_subscription_without_payment(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.create_promo_code("FREE7", "free_days", 7, 5, admin_id=999)

        app.handle_message(
            {
                "message_id": 5,
                "text": "/promo FREE7",
                "from": {"id": 201, "first_name": "Promo", "username": "promo"},
            }
        )

        self.assertTrue(app.store.is_subscription_active(201))
        self.assertEqual(app.store.get_payments(), [])
        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 1)
        self.assertIn("FREE7", send_calls[0]["text"])

    def test_promo_command_discount_changes_next_invoice(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.create_promo_code("SAVE20", "discount_percent", 20, 5, admin_id=999)

        app.handle_message(
            {
                "message_id": 6,
                "text": "/promo SAVE20",
                "from": {"id": 202, "first_name": "Promo", "username": "promo"},
            }
        )
        app.handle_message(
            {
                "message_id": 7,
                "text": "/buy",
                "from": {"id": 202, "first_name": "Promo", "username": "promo"},
            }
        )

        invoice_calls = fake_client.get_calls("send_invoice")
        self.assertEqual(len(invoice_calls), 1)
        params = invoice_calls[0]["params"]
        self.assertEqual(params["payload"], "subscription:202")
        self.assertEqual(params["prices"][0]["amount"], 200)
        self.assertEqual(app.store.get_user(202)["pendingPromoCode"], "SAVE20")

    def test_successful_payment_with_discount_promo_consumes_once(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.create_promo_code("SAVE20", "discount_percent", 20, 1, admin_id=999)

        app.handle_message(
            {
                "message_id": 8,
                "text": "/promo SAVE20",
                "from": {"id": 203, "first_name": "Promo", "username": "promo"},
            }
        )
        payment_message = {
            "message_id": 9,
            "from": {"id": 203, "first_name": "Promo", "username": "promo"},
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 200,
                "telegram_payment_charge_id": "charge_promo_203",
                "invoice_payload": "subscription:203",
            },
        }

        app.handle_message(payment_message)
        first_user = app.store.get_user(203)
        first_until = first_user["subscriptionUntil"]
        first_promo = app.store.get_promo_code("SAVE20")

        app.handle_message(payment_message)
        second_user = app.store.get_user(203)
        second_promo = app.store.get_promo_code("SAVE20")

        self.assertTrue(app.store.has_payment("charge_promo_203"))
        self.assertTrue(app.store.is_subscription_active(203))
        self.assertEqual(first_user["totalPaymentsCount"], 1)
        self.assertIsNone(first_user["pendingPromoCode"])
        self.assertIn("203", first_promo["usedBy"])
        self.assertEqual(second_user["subscriptionUntil"], first_until)
        self.assertEqual(second_user["totalPaymentsCount"], 1)
        self.assertEqual(list(second_promo["usedBy"].keys()), ["203"])


if __name__ == "__main__":
    unittest.main()

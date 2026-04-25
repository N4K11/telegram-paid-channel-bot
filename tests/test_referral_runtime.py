import tempfile
import unittest

from bot.app import SubscriptionBotApp
from config import Config
from store_py import create_store

try:
    from fakes import FakeTelegramClient
except ModuleNotFoundError:
    from tests.fakes import FakeTelegramClient


class ReferralRuntimeTests(unittest.TestCase):
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

    def make_app(self, fake_client=None):
        config = self.make_config()
        store = create_store(config.data_file_path)
        app = SubscriptionBotApp(config, store)
        app.telegram = fake_client or FakeTelegramClient()
        app.current_bot_token = config.bot_token
        app.current_api_base_url = config.telegram_api_base_url
        app._bootstrap()
        return app

    def test_start_referral_parameter_saves_referrer(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        referrer = app.store.ensure_user({"id": 601, "first_name": "Referrer", "username": "referrer"})

        app.handle_message(
            {
                "message_id": 1,
                "text": f"/start ref_{referrer['referralCode']}",
                "from": {"id": 602, "first_name": "Invitee", "username": "invitee"},
            }
        )

        invitee = app.store.get_user(602)
        self.assertEqual(invitee["referredBy"], 601)
        self.assertEqual(len(fake_client.get_calls("send_message")), 1)

    def test_self_referral_via_start_is_rejected(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        user = app.store.ensure_user({"id": 603, "first_name": "Self", "username": "self"})

        app.handle_message(
            {
                "message_id": 2,
                "text": f"/start ref_{user['referralCode']}",
                "from": {"id": 603, "first_name": "Self", "username": "self"},
            }
        )

        self.assertIsNone(app.store.get_user(603)["referredBy"])
        self.assertIn("собственный", fake_client.get_calls("send_message")[0]["text"].lower())

    def test_referral_reward_granted_after_successful_payment(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        referrer = app.store.ensure_user({"id": 604, "first_name": "Referrer", "username": "referrer"})

        app.handle_message(
            {
                "message_id": 3,
                "text": f"/start ref_{referrer['referralCode']}",
                "from": {"id": 605, "first_name": "Invitee", "username": "invitee"},
            }
        )
        before_referrer = app.store.get_user(604)

        app.handle_message(
            {
                "message_id": 4,
                "from": {"id": 605, "first_name": "Invitee", "username": "invitee"},
                "successful_payment": {
                    "currency": "XTR",
                    "total_amount": 250,
                    "telegram_payment_charge_id": "charge_referral_605",
                    "invoice_payload": "subscription:605",
                },
            }
        )

        after_referrer = app.store.get_user(604)
        self.assertGreater(after_referrer["subscriptionUntil"], before_referrer.get("subscriptionUntil") or 0)
        self.assertEqual(len(after_referrer["referralRewards"]), 1)
        self.assertEqual(after_referrer["referralRewards"][0]["referredUserId"], 605)

    def test_duplicate_payment_does_not_reward_twice(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        referrer = app.store.ensure_user({"id": 606, "first_name": "Referrer", "username": "referrer"})

        app.handle_message(
            {
                "message_id": 5,
                "text": f"/start ref_{referrer['referralCode']}",
                "from": {"id": 607, "first_name": "Invitee", "username": "invitee"},
            }
        )
        payment_message = {
            "message_id": 6,
            "from": {"id": 607, "first_name": "Invitee", "username": "invitee"},
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 250,
                "telegram_payment_charge_id": "charge_referral_607",
                "invoice_payload": "subscription:607",
            },
        }

        app.handle_message(payment_message)
        first_referrer = app.store.get_user(606)
        app.handle_message(payment_message)
        second_referrer = app.store.get_user(606)

        self.assertEqual(len(first_referrer["referralRewards"]), 1)
        self.assertEqual(len(second_referrer["referralRewards"]), 1)
        self.assertEqual(first_referrer["subscriptionUntil"], second_referrer["subscriptionUntil"])


if __name__ == "__main__":
    unittest.main()

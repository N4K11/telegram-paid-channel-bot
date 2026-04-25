import ast
import tempfile
import unittest
from pathlib import Path

from bot.app import SubscriptionBotApp
from bot.ui import UIProvider
from config import Config
from fakes import FakeTelegramClient
from store_py import create_store


class UserHandlerTests(unittest.TestCase):
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
        return app

    @staticmethod
    def _callback_values(markup):
        values = []
        for row in markup.get("inline_keyboard", []):
            for button in row:
                if "callback_data" in button:
                    values.append(button["callback_data"])
        return values

    def test_user_handlers_import_without_bot_app_cycle(self):
        for relative_path in [
            "bot/handlers/user.py",
            "bot/handlers/user_actions.py",
            "bot/handlers/user_render.py",
        ]:
            tree = ast.parse(Path(relative_path).read_text(encoding="utf-8-sig"), filename=relative_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotEqual(alias.name, "bot.app")
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, "bot.app")

    def test_user_public_api_preserved(self):
        app = self.make_app()
        self.assertTrue(callable(app.user_handler.handle_command))
        self.assertTrue(callable(app.user_handler.handle_callback))

    def test_start_command_still_renders_main_menu(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)

        app.user_handler.handle_command({"from": {"id": 201}}, "/start", None)

        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 1)
        self.assertIn("Тариф", send_calls[0]["text"])
        self.assertIn("reply_markup", send_calls[0]["extra"])

    def test_buy_callback_still_sends_invoice(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 202, "first_name": "Buyer", "username": "buyer"})

        app.user_handler.handle_callback(
            {
                "id": "cb-buy",
                "from": {"id": 202},
                "data": "buy",
                "message": {"message_id": 1},
            }
        )

        invoice_calls = fake_client.get_calls("send_invoice")
        self.assertEqual(len(invoice_calls), 1)
        self.assertEqual(invoice_calls[0]["params"]["payload"], "subscription:202")
        self.assertEqual(len(fake_client.get_calls("answer_callback_query")), 1)

    def test_join_link_callback_for_active_user(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 203, "first_name": "Active", "username": "active"})
        app.store.update_settings({"channelInviteLink": "https://t.me/+manual_link"})
        app.store.grant_subscription_days(203, 30)

        app.user_handler.handle_callback(
            {
                "id": "cb-join-active",
                "from": {"id": 203},
                "data": "join",
                "message": {"message_id": 3},
            }
        )

        edit_calls = fake_client.get_calls("edit_message_text")
        self.assertEqual(len(edit_calls), 1)
        keyboard = edit_calls[0]["extra"]["reply_markup"]["inline_keyboard"]
        self.assertEqual(keyboard[0][0]["url"], "https://t.me/+manual_link")
        self.assertEqual(keyboard[1][0]["callback_data"], "panel:main")

    def test_join_link_callback_for_inactive_user(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 204, "first_name": "Inactive", "username": "inactive"})

        app.user_handler.handle_callback(
            {
                "id": "cb-join-inactive",
                "from": {"id": 204},
                "data": "join",
                "message": {"message_id": 4},
            }
        )

        edit_calls = fake_client.get_calls("edit_message_text")
        self.assertEqual(len(edit_calls), 1)
        keyboard = edit_calls[0]["extra"]["reply_markup"]["inline_keyboard"]
        self.assertEqual(keyboard[0][0]["callback_data"], "buy")
        self.assertEqual(keyboard[1][0]["callback_data"], "panel:main")

    def test_help_and_support_callbacks_preserved(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 205, "first_name": "Helper", "username": "helper"})

        app.user_handler.handle_callback(
            {
                "id": "cb-help",
                "from": {"id": 205},
                "data": "user:help",
                "message": {"message_id": 5},
            }
        )

        edit_calls = fake_client.get_calls("edit_message_text")
        self.assertEqual(len(edit_calls), 1)
        self.assertIn("Справка по боту", edit_calls[0]["text"])

        _, main_markup = UIProvider.get_main_menu(
            {
                "settings": {
                    "subscriptionName": "Test Subscription",
                    "welcomeText": "Welcome",
                    "subscriptionPriceStars": 250,
                    "subscriptionDurationDays": 30,
                    "supportUsername": "support_manager",
                },
                "user": {"balanceStars": 0},
                "is_active": False,
                "effective_invite_link": "",
                "system": {"appTimezone": "Europe/Saratov"},
                "notice": None,
                "is_admin": False,
            }
        )
        support_buttons = [
            button
            for row in main_markup["inline_keyboard"]
            for button in row
            if button.get("text") == "🆘 Поддержка"
        ]
        self.assertEqual(len(support_buttons), 1)
        self.assertEqual(support_buttons[0]["url"], "https://t.me/support_manager")

    def test_unknown_user_callback_does_not_crash(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)

        app.user_handler.handle_callback(
            {
                "id": "cb-unknown",
                "from": {"id": 206},
                "data": "user:unknown:noop",
                "message": {"message_id": 6},
            }
        )

        answer_calls = fake_client.get_calls("answer_callback_query")
        self.assertEqual(len(answer_calls), 1)
        self.assertEqual(answer_calls[0]["callback_query_id"], "cb-unknown")

    def test_user_callback_data_preserved(self):
        _, main_markup = UIProvider.get_main_menu(
            {
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
        )
        callbacks = set(self._callback_values(main_markup))
        self.assertTrue({"buy", "join", "user:help", "buy_balance", "admin:menu"}.issubset(callbacks))

        _, help_markup = UIProvider.get_user_help("support_manager")
        self.assertEqual(set(self._callback_values(help_markup)), {"panel:main"})


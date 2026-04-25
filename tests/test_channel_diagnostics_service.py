import ast
import tempfile
import unittest
from pathlib import Path

from bot.app import SubscriptionBotApp
from bot.services import channel_diagnostics_service
from config import Config
from fakes import FakeTelegramClient
from store_py import create_store


class ChannelDiagnosticsFakeTelegramClient(FakeTelegramClient):
    def __init__(self, chat_member=None, failures=None, me=None):
        super().__init__(failures=failures)
        self.chat_member = dict(
            chat_member
            or {
                "status": "administrator",
                "user": {"id": 1},
                "can_invite_users": True,
                "can_restrict_members": True,
            }
        )
        self.me_info = dict(me or {"id": 1, "username": "diag_bot"})

    def get_me(self):
        self._record("get_me")
        self._maybe_fail("get_me")
        return dict(self.me_info)

    def get_chat_member(self, chat_id, user_id):
        self._record("get_chat_member", chat_id=chat_id, user_id=user_id)
        self._maybe_fail("get_chat_member", chat_id, user_id)
        return dict(self.chat_member)


class ChannelDiagnosticsServiceTests(unittest.TestCase):
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
        app.telegram = fake_client or ChannelDiagnosticsFakeTelegramClient()
        app.current_bot_token = config.bot_token
        app.current_api_base_url = config.telegram_api_base_url
        app._bootstrap()
        return app

    def test_channel_diagnostics_service_imports_without_bot_app_cycle(self):
        tree = ast.parse(
            Path("bot/services/channel_diagnostics_service.py").read_text(encoding="utf-8-sig"),
            filename="bot/services/channel_diagnostics_service.py",
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "bot.app")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "bot.app")

    def test_channel_check_all_ok(self):
        app = self.make_app(fake_client=ChannelDiagnosticsFakeTelegramClient())
        before = app.store.get_state()

        result = channel_diagnostics_service.run_channel_diagnostics(app)
        text = channel_diagnostics_service.format_channel_diagnostics(result)

        self.assertTrue(result["channelConfigured"])
        self.assertTrue(result["channelAccessOk"])
        self.assertTrue(result["isAdmin"])
        self.assertTrue(result["canInviteUsers"])
        self.assertTrue(result["canApproveJoinRequests"])
        self.assertTrue(result["canRestrictMembers"])
        self.assertTrue(result["inviteFlowAvailable"])
        self.assertEqual(before, app.store.get_state())
        self.assertIn("CHANNEL_ID прочитан", text)
        self.assertIn("Бот является администратором канала", text)

    def test_channel_check_bot_kicked(self):
        client = ChannelDiagnosticsFakeTelegramClient(
            failures={
                "get_chat_member": RuntimeError(
                    "Telegram API error at getChatMember: Forbidden: bot was kicked from the channel chat"
                )
            }
        )
        app = self.make_app(fake_client=client)

        result = channel_diagnostics_service.run_channel_diagnostics(app)
        text = channel_diagnostics_service.format_channel_diagnostics(result)

        self.assertEqual(result["errorKind"], "bot_kicked")
        self.assertFalse(result["channelAccessOk"])
        self.assertIn("Бот удалён из канала", text)

    def test_channel_check_bot_not_admin(self):
        client = ChannelDiagnosticsFakeTelegramClient(chat_member={"status": "member", "user": {"id": 1}})
        app = self.make_app(fake_client=client)

        result = channel_diagnostics_service.run_channel_diagnostics(app)
        text = channel_diagnostics_service.format_channel_diagnostics(result)

        self.assertFalse(result["isAdmin"])
        self.assertIn("Бот не является администратором канала.", result["warnings"])
        self.assertIn("Бот не администратор канала", text)

    def test_channel_check_missing_invite_permission(self):
        client = ChannelDiagnosticsFakeTelegramClient(
            chat_member={
                "status": "administrator",
                "user": {"id": 1},
                "can_invite_users": False,
                "can_restrict_members": True,
            }
        )
        app = self.make_app(fake_client=client)

        result = channel_diagnostics_service.run_channel_diagnostics(app)
        text = channel_diagnostics_service.format_channel_diagnostics(result)

        self.assertFalse(result["canInviteUsers"])
        self.assertFalse(result["canApproveJoinRequests"])
        self.assertIn("Нет права создавать invite links / approve join requests", text)

    def test_channel_check_missing_restrict_permission(self):
        client = ChannelDiagnosticsFakeTelegramClient(
            chat_member={
                "status": "administrator",
                "user": {"id": 1},
                "can_invite_users": True,
                "can_restrict_members": False,
            }
        )
        app = self.make_app(fake_client=client)

        result = channel_diagnostics_service.run_channel_diagnostics(app)
        text = channel_diagnostics_service.format_channel_diagnostics(result)

        self.assertFalse(result["canRestrictMembers"])
        self.assertIn("Нет права restrict/ban users", text)

    def test_channel_check_invalid_channel_id(self):
        client = ChannelDiagnosticsFakeTelegramClient(
            failures={
                "get_chat_member": RuntimeError(
                    "Telegram API error at getChatMember: Bad Request: chat not found"
                )
            }
        )
        app = self.make_app(fake_client=client, channel_id="-100999999999")

        result = channel_diagnostics_service.run_channel_diagnostics(app)
        text = channel_diagnostics_service.format_channel_diagnostics(result)

        self.assertEqual(result["errorKind"], "invalid_channel_id")
        self.assertIn("CHANNEL_ID невалиден", text)

    def test_channel_check_does_not_expose_token(self):
        token_like_error = (
            "Telegram API error at getChatMember: Forbidden: bad token 123456789:ABCDEF_token_hidden_example"
        )
        client = ChannelDiagnosticsFakeTelegramClient(
            failures={"get_chat_member": RuntimeError(token_like_error)}
        )
        app = self.make_app(fake_client=client)

        text = channel_diagnostics_service.format_channel_diagnostics(
            channel_diagnostics_service.run_channel_diagnostics(app)
        )

        self.assertNotIn("123456789:ABCDEF_token_hidden_example", text)
        self.assertIn("<redacted-token>", text)


if __name__ == "__main__":
    unittest.main()

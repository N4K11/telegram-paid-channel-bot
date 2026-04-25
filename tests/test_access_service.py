import ast
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.app import SubscriptionBotApp
from bot.services import access_service
from config import Config
from store_py import create_store
from fakes import FakeTelegramClient


class AccessServiceTests(unittest.TestCase):
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

    def test_access_service_module_imports_without_bot_app_cycle(self):
        module = __import__("bot.services.access_service", fromlist=["access_service"])
        self.assertIsNotNone(module)

        tree = ast.parse(Path("bot/services/access_service.py").read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "bot.app")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "bot.app")

    def test_manual_invite_link_has_priority(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.update_settings({"channelInviteLink": "https://t.me/+manual_link"})

        link = access_service.ensure_invite_link(app, force=False)

        self.assertEqual(link, "https://t.me/+manual_link")
        self.assertEqual(access_service.get_join_link(app), "https://t.me/+manual_link")
        self.assertEqual(fake_client.get_calls("create_chat_invite_link"), [])

    def test_refresh_invite_link_creates_join_request_link(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)

        link = access_service.refresh_invite_link(app)

        create_calls = fake_client.get_calls("create_chat_invite_link")
        self.assertEqual(len(create_calls), 1)
        self.assertEqual(create_calls[0]["chat_id"], "@privatechannel")
        self.assertTrue(create_calls[0]["creates_join_request"])
        self.assertEqual(link, "https://t.me/+fake_invite")
        self.assertEqual(app.store.get_meta()["joinInviteLink"], "https://t.me/+fake_invite")

    def test_handle_join_request_for_active_subscriber_approves(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 201, "first_name": "Active", "username": "active"})
        app.store.grant_subscription_days(201, 30)

        access_service.handle_chat_join_request(
            app,
            {"from": {"id": 201}, "chat": {"id": -100123456}},
        )

        approve_calls = fake_client.get_calls("approve_chat_join_request")
        self.assertEqual(len(approve_calls), 1)
        self.assertEqual(approve_calls[0]["chat_id"], "@privatechannel")
        user = app.store.get_user(201)
        self.assertIsNone(user["pendingJoinRequest"])
        self.assertEqual(user["channelMemberStatus"], "member")

    def test_handle_join_request_for_inactive_user_does_not_approve(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 202, "first_name": "Inactive", "username": "inactive"})

        access_service.handle_chat_join_request(
            app,
            {"from": {"id": 202}, "chat": {"id": -100123456}},
        )

        self.assertEqual(fake_client.get_calls("approve_chat_join_request"), [])
        user = app.store.get_user(202)
        self.assertIsNotNone(user["pendingJoinRequest"])
        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 1)
        self.assertIn("Заявка получена", send_calls[0]["text"])

    def test_approve_pending_request_clears_pending(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 203, "first_name": "Pending", "username": "pending"})
        app.store.grant_subscription_days(203, 30)
        app.store.set_user_pending_join_request(203, {"chatId": -100123456, "createdAt": int(time.time() * 1000)})

        approved = access_service.approve_pending_request(app, 203)

        self.assertTrue(approved)
        user = app.store.get_user(203)
        self.assertIsNone(user["pendingJoinRequest"])
        self.assertEqual(user["channelMemberStatus"], "member")

    def test_approve_pending_request_error_is_logged_not_raised_if_current_behavior(self):
        def approve_failure(chat_id, user_id):
            raise RuntimeError("approve failed")

        fake_client = FakeTelegramClient(failures={"approve_chat_join_request": approve_failure})
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 204, "first_name": "ApproveFail", "username": "approvefail"})
        app.store.grant_subscription_days(204, 30)
        app.store.set_user_pending_join_request(204, {"chatId": -100123456, "createdAt": int(time.time() * 1000)})

        with patch.object(app, "_log_error") as log_mock:
            approved = access_service.approve_pending_request(app, 204)

        self.assertFalse(approved)
        self.assertIsNotNone(app.store.get_user(204)["pendingJoinRequest"])
        self.assertTrue(any("Approval failed for 204" in str(call.args[0]) for call in log_mock.call_args_list))

    def test_revoke_user_subscription_ban_unban(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 205, "first_name": "Revoke", "username": "revoke"})
        app.store.grant_subscription_days(205, 30)
        app.store.set_user_channel_member_status(205, "member")

        access_service.revoke_user_subscription(app, 205, "expired")

        ban_calls = fake_client.get_calls("ban_chat_member")
        unban_calls = fake_client.get_calls("unban_chat_member")
        self.assertEqual(len(ban_calls), 1)
        self.assertEqual(len(unban_calls), 1)
        self.assertEqual(ban_calls[0]["chat_id"], "@privatechannel")
        self.assertEqual(unban_calls[0]["chat_id"], "@privatechannel")
        self.assertLessEqual(app.store.get_user(205)["subscriptionUntil"], int(time.time() * 1000))
        self.assertEqual(app.store.get_user(205)["channelMemberStatus"], "member")

    def test_revoke_user_subscription_error_behavior(self):
        def ban_failure(chat_id, user_id):
            raise RuntimeError("ban failed")

        fake_client = FakeTelegramClient(failures={"ban_chat_member": ban_failure})
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 206, "first_name": "RevokeFail", "username": "revokefail"})
        app.store.grant_subscription_days(206, 30)

        with patch.object(app, "_log_error") as log_mock:
            access_service.revoke_user_subscription(app, 206, "expired")

        self.assertLessEqual(app.store.get_user(206)["subscriptionUntil"], int(time.time() * 1000))
        self.assertTrue(any("Revoke channel access failed for 206" in str(call.args[0]) for call in log_mock.call_args_list))
        self.assertEqual(fake_client.get_calls("unban_chat_member"), [])

    def test_prune_expired_pending_join_requests_declines_old_requests(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        fixed_now = 1_700_000_000_000
        app.store.ensure_user({"id": 207, "first_name": "OldPending", "username": "oldpending"})
        app.store.set_user_pending_join_request(
            207,
            {"chatId": -100123456, "createdAt": fixed_now - app.JOIN_REQUEST_TTL_MS - 1},
        )

        declined = access_service.prune_expired_pending_join_requests(app, now_ms=fixed_now)

        self.assertEqual(declined, 1)
        decline_calls = fake_client.get_calls("decline_chat_join_request")
        self.assertEqual(len(decline_calls), 1)
        self.assertEqual(decline_calls[0]["user_id"], 207)
        self.assertIsNone(app.store.get_user(207)["pendingJoinRequest"])

    def test_bot_app_wrappers_delegate_to_access_service(self):
        app = self.make_app()

        with patch.object(access_service, "handle_chat_join_request", return_value="join_result") as join_mock:
            self.assertEqual(app.handle_chat_join_request({"from": {"id": 1}, "chat": {"id": 2}}), "join_result")
        join_mock.assert_called_once_with(app, {"from": {"id": 1}, "chat": {"id": 2}})

        with patch.object(access_service, "approve_pending_request", return_value=True) as approve_mock:
            self.assertTrue(app.approve_pending_request(1, force=True))
        approve_mock.assert_called_once_with(app, 1, force=True)

        with patch.object(access_service, "ensure_invite_link", return_value="invite") as ensure_mock:
            self.assertEqual(app.ensure_invite_link(force=True), "invite")
        ensure_mock.assert_called_once_with(app, force=True)

        with patch.object(access_service, "refresh_invite_link", return_value="refresh") as refresh_mock:
            self.assertEqual(app.refresh_invite_link(), "refresh")
        refresh_mock.assert_called_once_with(app)

        with patch.object(access_service, "revoke_user_subscription", return_value=None) as revoke_mock:
            self.assertIsNone(app.revoke_user_subscription(1, "expired"))
        revoke_mock.assert_called_once_with(app, 1, "expired")

        with patch.object(access_service, "send_join_link", return_value=None) as send_join_mock:
            self.assertIsNone(app.send_join_link(1))
        send_join_mock.assert_called_once_with(app, 1, callback_query=None)


if __name__ == "__main__":
    unittest.main()

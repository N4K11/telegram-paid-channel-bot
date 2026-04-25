import io
import logging
import tempfile
import time
import unittest
from unittest.mock import patch

from bot.app import SubscriptionBotApp
from bot.services import access_service
from bot.services import channel_diagnostics_service
from bot.services import health_service
from config import Config
from fakes import FakeTelegramClient
from store_py import create_store


class RuntimeLoggingFakeTelegramClient(FakeTelegramClient):
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


class LogCapture:
    def __init__(self, logger):
        from bot import logging_config

        self.logger = logger
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(logging_config.RedactingFormatter("%(message)s"))
        self.old_propagate = logger.propagate
        logger.propagate = False
        logger.addHandler(self.handler)

    def text(self):
        return self.stream.getvalue()

    def close(self):
        self.logger.removeHandler(self.handler)
        self.logger.propagate = self.old_propagate


class RuntimeLoggingTests(unittest.TestCase):
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
        app.telegram = fake_client or RuntimeLoggingFakeTelegramClient()
        app.current_bot_token = config.bot_token
        app.current_api_base_url = config.telegram_api_base_url
        app._bootstrap()
        return app

    def test_log_error_redacts_sensitive_values(self):
        app = self.make_app()
        capture = LogCapture(app.logger)
        self.addCleanup(capture.close)

        app._log_error(
            "Invite bootstrap error",
            RuntimeError("Telegram API error: bad token 123456789:ABCDEF_token_hidden_example https://t.me/+hiddeninvite"),
        )

        payload = capture.text()
        self.assertIn("event=telegram_api_error", payload)
        self.assertIn("<redacted-token>", payload)
        self.assertIn("<redacted-invite-link>", payload)
        self.assertNotIn("123456789:ABCDEF_token_hidden_example", payload)

    def test_successful_payment_logs_received_and_duplicate(self):
        app = self.make_app()
        capture = LogCapture(app.logger)
        self.addCleanup(capture.close)
        app.store.ensure_user({"id": 201, "first_name": "Log", "username": "log"})
        message = {
            "message_id": 1,
            "from": {"id": 201, "first_name": "Log", "username": "log"},
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 250,
                "telegram_payment_charge_id": "charge_log_201",
                "invoice_payload": "subscription:201",
            },
        }

        app.handle_message(message)
        app.handle_message(message)

        payload = capture.text()
        self.assertIn("event=payment_received", payload)
        self.assertIn("event=subscription_activated", payload)
        self.assertIn("event=payment_duplicate", payload)

    def test_access_events_logged(self):
        app = self.make_app()
        capture = LogCapture(app.logger)
        self.addCleanup(capture.close)
        now_ms = int(time.time() * 1000)

        app.store.ensure_user({"id": 202, "first_name": "Access", "username": "access"})
        app.store.grant_subscription_days(202, 30)
        app.handle_chat_join_request({"from": {"id": 202}, "chat": {"id": -100123456}})
        app.store.set_user_pending_join_request(202, {"chatId": -100123456, "createdAt": now_ms - app.JOIN_REQUEST_TTL_MS - 1})
        access_service.decline_pending_join_request(app, 202)
        app.revoke_user_subscription(202, "expired")

        payload = capture.text()
        self.assertIn("event=join_request_approved", payload)
        self.assertIn("event=join_request_declined", payload)
        self.assertIn("event=subscription_revoked", payload)

    def test_maintenance_logs_started_and_finished(self):
        app = self.make_app()
        capture = LogCapture(app.logger)
        self.addCleanup(capture.close)
        expired_at = int(time.time() * 1000) - 1000
        app.store.ensure_user({"id": 203, "first_name": "Expired", "username": "expired"})
        app.store.update_user_fields(203, {"subscriptionUntil": expired_at, "lastAccessRevokedAt": None})

        app.run_subscription_maintenance()

        payload = capture.text()
        self.assertIn("event=maintenance_started", payload)
        self.assertIn("event=maintenance_finished", payload)

    def test_channel_diagnostics_and_health_failures_logged(self):
        app = self.make_app(
            fake_client=RuntimeLoggingFakeTelegramClient(
                failures={"get_chat_member": RuntimeError("Telegram API error at getChatMember: Forbidden: bad token 123456789:ABCDEF_token_hidden_example")}
            )
        )
        capture = LogCapture(app.logger)
        self.addCleanup(capture.close)

        channel_diagnostics_service.run_channel_diagnostics(app)
        with patch.object(
            health_service,
            "_check_store_writable",
            return_value={"ok": False, "error": "permission denied"},
        ):
            health_service.get_health_status(app)

        payload = capture.text()
        self.assertIn("event=channel_diagnostics_failed", payload)
        self.assertIn("event=health_check_failed", payload)
        self.assertIn("<redacted-token>", payload)

    def test_manual_recovery_logs_event(self):
        app = self.make_app()
        capture = LogCapture(app.logger)
        self.addCleanup(capture.close)
        app.store.ensure_user({"id": 204, "first_name": "Recover", "username": "recover"})

        app.manual_recover_payment_access(999, 204, 7, "manual_check")

        payload = capture.text()
        self.assertIn("event=admin_recovery_used", payload)


if __name__ == "__main__":
    unittest.main()

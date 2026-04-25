import tempfile
import time
import unittest
from unittest.mock import patch

from bot.app import SubscriptionBotApp
from config import Config
from store_py import create_store
from fakes import FakeTelegramClient


class RuntimeFakeTelegramTests(unittest.TestCase):
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
            welcome_text="Р В Р’В Р Р†Р вЂљРЎСљР В Р’В Р РЋРІР‚СћР В Р’В Р вЂ™Р’В±Р В Р Р‹Р В РІР‚С™Р В Р’В Р РЋРІР‚Сћ Р В Р’В Р РЋРІР‚вЂќР В Р’В Р РЋРІР‚СћР В Р’В Р вЂ™Р’В¶Р В Р’В Р вЂ™Р’В°Р В Р’В Р вЂ™Р’В»Р В Р’В Р РЋРІР‚СћР В Р’В Р В РІР‚В Р В Р’В Р вЂ™Р’В°Р В Р Р‹Р Р†Р вЂљРЎв„ўР В Р Р‹Р В Р вЂ°.",
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

    @staticmethod
    def _callback_values(markup):
        callback_values = []
        for row in markup.get("inline_keyboard", []):
            for button in row:
                if "callback_data" in button:
                    callback_values.append(button["callback_data"])
        return callback_values

    def test_user_start_sends_or_edits_main_menu(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)

        app.handle_message(
            {
                "message_id": 1,
                "text": "/start",
                "from": {"id": 101, "first_name": "Ivan", "username": "ivan"},
            }
        )

        self.assertIsNotNone(app.store.get_user(101))
        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 1)
        self.assertIn("reply_markup", send_calls[0]["extra"])

    def test_buy_access_sends_invoice(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)

        app.handle_message(
            {
                "message_id": 2,
                "text": "/buy",
                "from": {"id": 102, "first_name": "Petr", "username": "petr"},
            }
        )

        invoice_calls = fake_client.get_calls("send_invoice")
        self.assertEqual(len(invoice_calls), 1)
        params = invoice_calls[0]["params"]
        self.assertEqual(params["payload"], "subscription:102")
        self.assertEqual(params["prices"][0]["amount"], app.store.get_settings()["subscriptionPriceStars"])

    def test_successful_payment_activates_subscription(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 103, "first_name": "Mila", "username": "mila"})

        payment_message = {
            "message_id": 3,
            "from": {"id": 103, "first_name": "Mila", "username": "mila"},
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 250,
                "telegram_payment_charge_id": "charge_103",
                "invoice_payload": "subscription:103",
            },
        }

        app.handle_message(payment_message)
        first_user = app.store.get_user(103)
        first_until = first_user["subscriptionUntil"]

        self.assertTrue(app.store.has_payment("charge_103"))
        self.assertTrue(app.store.is_subscription_active(103))
        self.assertEqual(first_user["totalPaymentsCount"], 1)
        self.assertEqual(len(app.store.get_payments()), 1)

        app.handle_message(payment_message)
        second_user = app.store.get_user(103)

        self.assertEqual(second_user["subscriptionUntil"], first_until)
        self.assertEqual(second_user["totalPaymentsCount"], 1)
        self.assertEqual(len(app.store.get_payments()), 1)

    def test_successful_payment_uses_atomic_store_flow(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 110, "first_name": "Atomic", "username": "atomic"})
        payment_message = {
            "message_id": 12,
            "from": {"id": 110, "first_name": "Atomic", "username": "atomic"},
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 250,
                "telegram_payment_charge_id": "charge_110",
                "invoice_payload": "subscription:110",
            },
        }

        with patch.object(app.store, "record_payment", side_effect=AssertionError("legacy payment path used")), \
             patch.object(app.store, "activate_subscription_from_payment", side_effect=AssertionError("legacy activation path used")), \
             patch.object(app.store, "record_payment_and_activate_subscription", wraps=app.store.record_payment_and_activate_subscription) as atomic_mock:
            app.handle_message(payment_message)

        atomic_mock.assert_called_once()
        self.assertTrue(app.store.has_payment("charge_110"))
        self.assertTrue(app.store.is_subscription_active(110))

    def test_successful_payment_duplicate_does_not_extend_twice(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 111, "first_name": "Repeat", "username": "repeat"})
        payment_message = {
            "message_id": 13,
            "from": {"id": 111, "first_name": "Repeat", "username": "repeat"},
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 250,
                "telegram_payment_charge_id": "charge_111",
                "invoice_payload": "subscription:111",
            },
        }

        app.handle_message(payment_message)
        first_user = app.store.get_user(111)
        first_until = first_user["subscriptionUntil"]
        first_messages = len(fake_client.get_calls("send_message"))

        app.handle_message(payment_message)
        second_user = app.store.get_user(111)

        self.assertEqual(second_user["subscriptionUntil"], first_until)
        self.assertEqual(second_user["totalPaymentsCount"], 1)
        self.assertEqual(len(app.store.get_payments()), 1)
        self.assertEqual(len(fake_client.get_calls("send_message")), first_messages)

    def test_successful_payment_store_failure_does_not_ack_as_success_if_state_not_saved(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 112, "first_name": "Failure", "username": "failure"})
        update = {
            "update_id": 77,
            "message": {
                "message_id": 14,
                "from": {"id": 112, "first_name": "Failure", "username": "failure"},
                "successful_payment": {
                    "currency": "XTR",
                    "total_amount": 250,
                    "telegram_payment_charge_id": "charge_112",
                    "invoice_payload": "subscription:112",
                },
            },
        }

        with patch.object(app.store, "record_payment_and_activate_subscription", side_effect=OSError("save failed")), \
             patch.object(app, "_log_error") as log_mock:
            app._process_polled_update(update)

        self.assertFalse(app.store.has_payment("charge_112"))
        self.assertFalse(app.store.is_subscription_active(112))
        self.assertEqual(fake_client.get_calls("send_message"), [])
        self.assertTrue(any("Update handling error for 77" in str(call.args[0]) for call in log_mock.call_args_list))

    def test_successful_payment_with_pending_join_request_approves_request(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 113, "first_name": "Pending", "username": "pending"})
        app.store.set_user_pending_join_request(113, {"chatId": -100123456, "createdAt": int(time.time() * 1000)})
        payment_message = {
            "message_id": 15,
            "from": {"id": 113, "first_name": "Pending", "username": "pending"},
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 250,
                "telegram_payment_charge_id": "charge_113",
                "invoice_payload": "subscription:113",
            },
        }

        app.handle_message(payment_message)

        approve_calls = fake_client.get_calls("approve_chat_join_request")
        self.assertEqual(len(approve_calls), 1)
        self.assertEqual(approve_calls[0]["user_id"], 113)
        self.assertIsNone(app.store.get_user(113)["pendingJoinRequest"])
        self.assertEqual(app.store.get_user(113)["channelMemberStatus"], "member")

    def test_successful_payment_keeps_subscription_when_pending_approve_fails(self):
        def approve_failure(chat_id, user_id):
            raise RuntimeError("approve failed")

        fake_client = FakeTelegramClient(failures={"approve_chat_join_request": approve_failure})
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 114, "first_name": "ApproveFail", "username": "approvefail"})
        app.store.set_user_pending_join_request(114, {"chatId": -100123456, "createdAt": int(time.time() * 1000)})
        payment_message = {
            "message_id": 16,
            "from": {"id": 114, "first_name": "ApproveFail", "username": "approvefail"},
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 250,
                "telegram_payment_charge_id": "charge_114",
                "invoice_payload": "subscription:114",
            },
        }

        with patch.object(app, "_log_error") as log_mock:
            app.handle_message(payment_message)

        self.assertTrue(app.store.has_payment("charge_114"))
        self.assertTrue(app.store.is_subscription_active(114))
        self.assertIsNotNone(app.store.get_user(114)["pendingJoinRequest"])
        self.assertTrue(any("Approval failed for 114" in str(call.args[0]) for call in log_mock.call_args_list))

    def test_join_request_approved_for_active_subscriber(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        app.store.ensure_user({"id": 104, "first_name": "Oleg", "username": "oleg"})
        app.store.grant_subscription_days(104, 30)

        app.handle_chat_join_request(
            {
                "from": {"id": 104},
                "chat": {"id": -100123456},
            }
        )

        approve_calls = fake_client.get_calls("approve_chat_join_request")
        self.assertEqual(len(approve_calls), 1)
        self.assertEqual(approve_calls[0]["chat_id"], "@privatechannel")
        user = app.store.get_user(104)
        self.assertIsNone(user["pendingJoinRequest"])
        self.assertEqual(user["channelMemberStatus"], "member")

    def test_expired_subscription_revoke_does_not_stop_on_single_error(self):
        def ban_failure(chat_id, user_id):
            if user_id == 105:
                raise RuntimeError("ban failed")

        fake_client = FakeTelegramClient(failures={"ban_chat_member": ban_failure})
        app = self.make_app(fake_client=fake_client)
        expired_at = int(time.time() * 1000) - 60_000

        for user_id in (105, 106):
            app.store.ensure_user({"id": user_id, "first_name": f"User{user_id}", "username": f"user{user_id}"})
            app.store.update_user_fields(user_id, {"subscriptionUntil": expired_at, "lastAccessRevokedAt": None})

        with patch.object(app, "_log_error") as log_mock:
            app.run_subscription_maintenance()

        ban_calls = fake_client.get_calls("ban_chat_member")
        unban_calls = fake_client.get_calls("unban_chat_member")
        self.assertEqual(sorted(call["user_id"] for call in ban_calls), [105, 106])
        self.assertEqual([call["user_id"] for call in unban_calls], [106])
        self.assertIsNotNone(app.store.get_user(105)["lastAccessRevokedAt"])
        self.assertIsNotNone(app.store.get_user(106)["lastAccessRevokedAt"])
        self.assertTrue(any("Revoke channel access failed for 105" in str(call.args[0]) for call in log_mock.call_args_list))

    def test_admin_payment_diag_requires_admin(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client, admin_telegram_id="999")
        app.store.ensure_user({"id": 120, "first_name": "DiagTarget", "username": "diagtarget"})

        app.handle_message(
            {
                "message_id": 17,
                "text": "/admin_payment_diag 120",
                "from": {"id": 121, "first_name": "User", "username": "user"},
            }
        )

        denied_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(denied_calls), 1)
        self.assertIn("/admin_login", denied_calls[0]["text"])

    def test_admin_payment_diag_outputs_recovery_warning(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client, admin_telegram_id="999")
        app.store.ensure_user({"id": 122, "first_name": "DiagTarget", "username": "diagtarget"})
        app.store.record_payment(
            {
                "telegramPaymentChargeId": "charge_diag_cmd",
                "userId": 122,
                "totalAmount": 250,
                "paidAt": int(time.time() * 1000),
                "invoicePayload": "subscription:122",
                "currency": "XTR",
            }
        )

        app.handle_message(
            {
                "message_id": 18,
                "text": "/admin_payment_diag 122",
                "from": {"id": 999, "first_name": "Admin", "username": "boss"},
            }
        )

        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 1)
        diag_text = send_calls[0]["text"]
        self.assertIn("Автоматическое восстановление отключено", diag_text)
        self.assertIn("Проверьте платёж вручную", diag_text)
        self.assertIn("/admin_recover_payment 122 30 manual_verification", diag_text)

    def test_admin_payment_anomalies_requires_admin(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client, admin_telegram_id="999")

        app.handle_message(
            {
                "message_id": 181,
                "text": "/admin_payment_anomalies",
                "from": {"id": 1221, "first_name": "User", "username": "user"},
            }
        )

        denied_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(denied_calls), 1)
        self.assertIn("/admin_login", denied_calls[0]["text"])

    def test_admin_payment_anomalies_lists_suspicious_users(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client, admin_telegram_id="999")
        app.store.ensure_user({"id": 124, "first_name": "Anomaly", "username": "anomaly"})
        app.store.record_payment(
            {
                "telegramPaymentChargeId": "charge_anomaly_cmd",
                "userId": 124,
                "totalAmount": 250,
                "paidAt": int(time.time() * 1000),
                "invoicePayload": "subscription:124",
                "currency": "XTR",
            }
        )

        app.handle_message(
            {
                "message_id": 182,
                "text": "/admin_payment_anomalies",
                "from": {"id": 999, "first_name": "Admin", "username": "boss"},
            }
        )

        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 1)
        text = send_calls[0]["text"]
        self.assertIn("124", text)
        self.assertIn("/admin_payment_diag 124", text)
        self.assertIn("Автоматическое восстановление отключено", text)

    def test_admin_payment_anomalies_empty_message(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client, admin_telegram_id="999")

        app.handle_message(
            {
                "message_id": 183,
                "text": "/admin_payment_anomalies 5",
                "from": {"id": 999, "first_name": "Admin", "username": "boss"},
            }
        )

        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 1)
        self.assertIn("не найдено", send_calls[0]["text"])

    def test_admin_payment_anomalies_callback_renders_list(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client, admin_telegram_id="999")
        app.store.ensure_user({"id": 125, "first_name": "CallbackAnomaly", "username": "callback_anomaly"})
        app.store.record_payment(
            {
                "telegramPaymentChargeId": "charge_callback_anomaly",
                "userId": 125,
                "totalAmount": 250,
                "paidAt": int(time.time() * 1000),
                "invoicePayload": "subscription:125",
                "currency": "XTR",
            }
        )

        app.handle_message(
            {
                "message_id": 184,
                "text": "/admin",
                "from": {"id": 999, "first_name": "Admin", "username": "boss"},
            }
        )

        app.handle_callback_query(
            {
                "id": "cb_payment_anomalies",
                "data": "admin:payment_anomalies",
                "from": {"id": 999, "first_name": "Admin", "username": "boss"},
                "message": {"message_id": 1},
            }
        )

        edit_calls = fake_client.get_calls("edit_message_text")
        self.assertEqual(len(edit_calls), 1)
        self.assertIn("/admin_payment_diag 125", edit_calls[0]["text"])
        answer_calls = fake_client.get_calls("answer_callback_query")
        self.assertEqual(len(answer_calls), 1)
    def test_manual_recovery_command_grants_access_without_changing_payment_totals(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client, admin_telegram_id="999")
        app.store.ensure_user({"id": 123, "first_name": "Recover", "username": "recover"})
        app.store.record_payment(
            {
                "telegramPaymentChargeId": "charge_recover_cmd",
                "userId": 123,
                "totalAmount": 250,
                "paidAt": int(time.time() * 1000),
                "invoicePayload": "subscription:123",
                "currency": "XTR",
            }
        )
        before_user = app.store.get_user(123)
        before_payments = app.store.get_payments()

        app.handle_message(
            {
                "message_id": 19,
                "text": "/admin_recover_payment 123 15 manual_verification",
                "from": {"id": 999, "first_name": "Admin", "username": "boss"},
            }
        )

        after_user = app.store.get_user(123)
        audit = app.store.get_audit_log(limit=10)
        self.assertGreater(after_user["subscriptionUntil"], before_user.get("subscriptionUntil") or 0)
        self.assertEqual(after_user["totalSpentStars"], before_user["totalSpentStars"])
        self.assertEqual(after_user["totalPaymentsCount"], before_user["totalPaymentsCount"])
        self.assertEqual(app.store.get_payments(), before_payments)
        recovery_entries = [entry for entry in audit if entry.get("type") == "manual_payment_recovery"]
        self.assertTrue(recovery_entries)
        self.assertEqual(recovery_entries[0]["adminId"], 999)

    def test_admin_panel_opens_for_authorized_admin(self):
        authorized_client = FakeTelegramClient()
        authorized_app = self.make_app(fake_client=authorized_client, admin_telegram_id="999")

        authorized_app.handle_message(
            {
                "message_id": 4,
                "text": "/admin",
                "from": {"id": 999, "first_name": "Admin", "username": "boss"},
            }
        )

        auth_send_calls = authorized_client.get_calls("send_message")
        self.assertEqual(len(auth_send_calls), 1)
        auth_callbacks = self._callback_values(auth_send_calls[0]["extra"]["reply_markup"])
        self.assertIn("admin:stats", auth_callbacks)
        self.assertIn("admin:payment_anomalies", auth_callbacks)

        unauthorized_client = FakeTelegramClient()
        unauthorized_app = self.make_app(fake_client=unauthorized_client, admin_telegram_id="999")

        unauthorized_app.handle_message(
            {
                "message_id": 5,
                "text": "/admin",
                "from": {"id": 107, "first_name": "User", "username": "user"},
            }
        )

        denied_calls = unauthorized_client.get_calls("send_message")
        self.assertEqual(len(denied_calls), 1)
        self.assertIn("/admin_login", denied_calls[0]["text"])

    def test_polling_resilience_processes_good_update_after_bad_one(self):
        fake_client = FakeTelegramClient()
        app = self.make_app(fake_client=fake_client)
        original_handle_message = app.handle_message
        updates = [
            {
                "update_id": 1,
                "message": {
                    "message_id": 10,
                    "text": "/boom",
                    "from": {"id": 108, "first_name": "Bad", "username": "bad"},
                },
            },
            {
                "update_id": 2,
                "message": {
                    "message_id": 11,
                    "text": "/start",
                    "from": {"id": 109, "first_name": "Good", "username": "good"},
                },
            },
        ]

        def get_updates(offset, timeout_seconds, allowed_updates):
            app.is_stopping = True
            return updates

        def flaky_handle_message(message):
            if message.get("text") == "/boom":
                raise RuntimeError("boom")
            return original_handle_message(message)

        fake_client.get_updates = get_updates

        with patch.object(app, "handle_message", side_effect=flaky_handle_message), \
             patch.object(app, "_log_error") as log_mock:
            app.poll_loop()

        send_calls = fake_client.get_calls("send_message")
        self.assertEqual(len(send_calls), 1)
        self.assertEqual(app.store.get_meta()["lastUpdateId"], 2)
        self.assertTrue(any("Update handling error for 1" in str(call.args[0]) for call in log_mock.call_args_list))


if __name__ == "__main__":
    unittest.main()




import ast
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bot.app import SubscriptionBotApp
from bot.services import payment_service
from config import Config
from store_py import create_store


class FakeStore:
    def __init__(self, result=None):
        self.settings = {
            "subscriptionName": "Test Subscription",
            "subscriptionDescription": "Test private access",
            "subscriptionPriceStars": 250,
            "subscriptionDurationDays": 30,
        }
        self.result = result or {"status": "processed", "payment": {}, "user": {}}
        self.calls = []
        self.users = {}
        self.promo_codes = {}
        self.cleared_pending = []

    def get_settings(self):
        return dict(self.settings)

    def get_user(self, user_id):
        stored = self.users.get(int(user_id))
        if stored is None:
            return {"id": int(user_id), "pendingPromoCode": None}
        return dict(stored)

    def get_promo_code(self, code):
        promo = self.promo_codes.get(str(code or "").strip().upper())
        return dict(promo) if promo else None

    def clear_user_pending_promo_code(self, user_id):
        self.cleared_pending.append(int(user_id))
        current = self.users.setdefault(int(user_id), {"id": int(user_id), "pendingPromoCode": None})
        current["pendingPromoCode"] = None
        return dict(current)

    def record_payment_and_activate_subscription(self, user_id, payment, settings, promo_code=None):
        self.calls.append(
            {
                "user_id": user_id,
                "payment": dict(payment),
                "settings": dict(settings),
                "promo_code": promo_code,
            }
        )
        return dict(self.result)


class FakeTelegram:
    def __init__(self):
        self.invoice_calls = []
        self.pre_checkout_calls = []

    def send_invoice(self, params):
        self.invoice_calls.append(dict(params))
        return {"message_id": 1}

    def answer_pre_checkout_query(self, pre_checkout_query_id, ok, error_message=""):
        self.pre_checkout_calls.append(
            {
                "pre_checkout_query_id": pre_checkout_query_id,
                "ok": ok,
                "error_message": error_message,
            }
        )
        return True


class PaymentServiceTests(unittest.TestCase):
    def make_service_app(self, result=None):
        store = FakeStore(result=result)
        telegram = FakeTelegram()
        app = SimpleNamespace()
        app.store = store
        app.telegram = telegram
        app.get_telegram = lambda: telegram
        app._now_ms = lambda: 1_700_000_000_000
        app.approve_pending_request = Mock()
        app.send_main_menu = Mock()
        return app, store, telegram

    def make_runtime_app(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        db_path = str(Path(tempdir.name) / "db.json")
        config = Config(
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
            data_file_path=db_path,
            session_secret="session-secret",
            telegram_api_base_url="https://api.telegram.org",
        )
        return SubscriptionBotApp(config, create_store(db_path))

    def test_payment_payload_contract(self):
        self.assertEqual(payment_service.build_payment_payload(123), "subscription:123")
        self.assertEqual(payment_service.parse_payment_payload("subscription:123"), 123)
        self.assertIsNone(payment_service.parse_payment_payload(""))
        self.assertIsNone(payment_service.parse_payment_payload("subscription:"))
        self.assertIsNone(payment_service.parse_payment_payload("subscription:abc"))
        self.assertIsNone(payment_service.parse_payment_payload("other:123"))

    def test_payment_service_module_imports_without_bot_app_cycle(self):
        module = __import__("bot.services.payment_service", fromlist=["payment_service"])
        self.assertIsNotNone(module)

        tree = ast.parse(Path("bot/services/payment_service.py").read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "bot.app")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "bot.app")

    def test_handle_successful_payment_uses_atomic_store_method(self):
        app, store, _ = self.make_service_app()
        message = {
            "from": {"id": 123},
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 250,
                "telegram_payment_charge_id": "charge_123",
                "invoice_payload": "subscription:123",
            },
        }

        result = payment_service.handle_successful_payment(app, message)

        self.assertEqual(result["status"], "processed")
        self.assertEqual(len(store.calls), 1)
        self.assertEqual(store.calls[0]["user_id"], 123)
        self.assertEqual(store.calls[0]["payment"]["invoicePayload"], "subscription:123")
        self.assertIsNone(store.calls[0]["promo_code"])
        app.approve_pending_request.assert_called_once_with(123)
        app.send_main_menu.assert_called_once_with(123, notice="Оплата принята! Доступ открыт.")

    def test_handle_successful_payment_passes_applied_promo_code_to_atomic_store(self):
        app, store, _ = self.make_service_app()
        store.users[125] = {"id": 125, "pendingPromoCode": "SAVE20"}
        store.promo_codes["SAVE20"] = {
            "code": "SAVE20",
            "type": "discount_percent",
            "value": 20,
            "maxUses": 5,
            "enabled": True,
            "usedBy": {},
        }
        message = {
            "from": {"id": 125},
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 200,
                "telegram_payment_charge_id": "charge_125",
                "invoice_payload": "subscription:125",
            },
        }

        result = payment_service.handle_successful_payment(app, message)

        self.assertEqual(result["status"], "processed")
        self.assertEqual(store.calls[0]["promo_code"], "SAVE20")
        app.approve_pending_request.assert_called_once_with(125)

    def test_handle_successful_payment_approves_referrer_only_when_pending_request_exists(self):
        app, store, _ = self.make_service_app(
            result={"status": "processed", "payment": {}, "user": {}, "rewardedReferrerId": 777}
        )
        store.users[777] = {"id": 777, "pendingJoinRequest": {"chatId": -100123}}
        message = {
            "from": {"id": 126},
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 250,
                "telegram_payment_charge_id": "charge_126",
                "invoice_payload": "subscription:126",
            },
        }

        payment_service.handle_successful_payment(app, message)

        self.assertEqual(
            app.approve_pending_request.call_args_list,
            [unittest.mock.call(126), unittest.mock.call(777)],
        )

    def test_handle_successful_payment_duplicate_does_not_send_second_success(self):
        app, _, _ = self.make_service_app(result={"status": "duplicate", "payment": {}, "user": {}})
        message = {
            "from": {"id": 124},
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 250,
                "telegram_payment_charge_id": "charge_124",
                "invoice_payload": "subscription:124",
            },
        }

        result = payment_service.handle_successful_payment(app, message)

        self.assertEqual(result["status"], "duplicate")
        app.approve_pending_request.assert_not_called()
        app.send_main_menu.assert_not_called()

    def test_handle_pre_checkout_accepts_valid_payload(self):
        app, _, telegram = self.make_service_app()

        payment_service.handle_pre_checkout(
            app,
            {"id": "pq_ok", "invoice_payload": "subscription:123"},
        )

        self.assertEqual(
            telegram.pre_checkout_calls,
            [{"pre_checkout_query_id": "pq_ok", "ok": True, "error_message": ""}],
        )

    def test_handle_pre_checkout_rejects_invalid_payload(self):
        app, _, telegram = self.make_service_app()

        payment_service.handle_pre_checkout(
            app,
            {"id": "pq_bad", "invoice_payload": "broken_payload"},
        )

        self.assertEqual(
            telegram.pre_checkout_calls,
            [{"pre_checkout_query_id": "pq_bad", "ok": False, "error_message": "Ошибка"}],
        )

    def test_handle_buy_access_sends_invoice(self):
        app, store, telegram = self.make_service_app()

        payment_service.handle_buy_access(app, 555)

        self.assertEqual(len(telegram.invoice_calls), 1)
        invoice = telegram.invoice_calls[0]
        self.assertEqual(invoice["chat_id"], 555)
        self.assertEqual(invoice["payload"], "subscription:555")
        self.assertEqual(invoice["prices"][0]["amount"], store.settings["subscriptionPriceStars"])
        self.assertEqual(invoice["title"], store.settings["subscriptionName"])
        self.assertEqual(invoice["description"], store.settings["subscriptionDescription"])

    def test_bot_app_wrappers_delegate_to_payment_service(self):
        app = self.make_runtime_app()

        with patch.object(payment_service, "handle_buy_access", return_value="invoice_result") as buy_mock:
            self.assertEqual(app.send_invoice(321), "invoice_result")
        buy_mock.assert_called_once_with(app, 321, plan_id=None)

        with patch.object(payment_service, "handle_pre_checkout", return_value="pre_checkout_result") as pre_mock:
            self.assertEqual(app.handle_pre_checkout_query({"id": "pq"}), "pre_checkout_result")
        pre_mock.assert_called_once_with(app, {"id": "pq"})

        with patch.object(payment_service, "handle_successful_payment", return_value="success_result") as payment_mock:
            self.assertEqual(app.handle_successful_payment({"successful_payment": {}, "from": {"id": 1}}), "success_result")
        payment_mock.assert_called_once_with(app, {"successful_payment": {}, "from": {"id": 1}})


if __name__ == "__main__":
    unittest.main()

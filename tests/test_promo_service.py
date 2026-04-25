import ast
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from bot.services import plan_service, promo_service
from store_py import create_store


class PromoServiceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db_path = str(Path(self.tempdir.name) / "db.json")

    def make_app(self):
        store = create_store(self.db_path)
        app = SimpleNamespace(store=store, approve_pending_request=Mock())
        return app, store

    @staticmethod
    def ensure_user(store, user_id=1, username="promo"):
        return store.ensure_user({"id": user_id, "first_name": f"User{user_id}", "username": username})

    def test_promo_service_imports_without_bot_app_cycle(self):
        tree = ast.parse(Path("bot/services/promo_service.py").read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "bot.app")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "bot.app")

    def test_promo_not_found(self):
        app, store = self.make_app()
        self.ensure_user(store, 1)

        result = promo_service.apply_user_promo(app, 1, "MISSING")

        self.assertEqual(result["status"], "not_found")
        self.assertIsNone(store.get_user(1)["pendingPromoCode"])

    def test_disabled_promo(self):
        app, store = self.make_app()
        self.ensure_user(store, 2)
        store.create_promo_code("OFF7", "free_days", 7, 5)
        store.disable_promo_code("OFF7")

        result = promo_service.apply_user_promo(app, 2, "OFF7")

        self.assertEqual(result["status"], "disabled")
        self.assertFalse(store.is_subscription_active(2))

    def test_max_uses_reached(self):
        app, store = self.make_app()
        self.ensure_user(store, 3, "promo3")
        self.ensure_user(store, 4, "promo4")
        store.create_promo_code("ONCE7", "free_days", 7, 1)

        first = promo_service.apply_user_promo(app, 3, "ONCE7")
        second = promo_service.apply_user_promo(app, 4, "ONCE7")

        self.assertEqual(first["status"], "processed")
        self.assertEqual(second["status"], "max_uses_reached")
        self.assertFalse(store.is_subscription_active(4))

    def test_repeat_use_forbidden(self):
        app, store = self.make_app()
        self.ensure_user(store, 5, "promo5")
        store.create_promo_code("REPEAT7", "free_days", 7, 5)

        first = promo_service.apply_user_promo(app, 5, "REPEAT7")
        second = promo_service.apply_user_promo(app, 5, "REPEAT7")

        self.assertEqual(first["status"], "processed")
        self.assertEqual(second["status"], "already_used")

    def test_free_days_grants_subscription_without_fake_payment(self):
        app, store = self.make_app()
        self.ensure_user(store, 6, "promo6")
        store.create_promo_code("FREE7", "free_days", 7, 5)

        result = promo_service.apply_user_promo(app, 6, "FREE7")

        self.assertEqual(result["status"], "processed")
        self.assertTrue(store.is_subscription_active(6))
        self.assertEqual(store.get_payments(), [])
        app.approve_pending_request.assert_called_once_with(6)

    def test_discount_changes_invoice_amount(self):
        app, store = self.make_app()
        self.ensure_user(store, 7, "promo7")
        store.create_promo_code("SAVE20", "discount_percent", 20, 5)

        result = promo_service.apply_user_promo(app, 7, "SAVE20")
        plan = plan_service.get_default_plan(store.get_settings())
        promo_context = promo_service.get_pending_discount_context(store, 7, plan)

        self.assertEqual(result["status"], "pending_invoice")
        self.assertEqual(store.get_user(7)["pendingPromoCode"], "SAVE20")
        self.assertEqual(promo_context["status"], "applied")
        self.assertEqual(promo_context["finalAmount"], 200)

    def test_audit_log_written_for_free_days_promo(self):
        app, store = self.make_app()
        self.ensure_user(store, 8, "promo8")
        store.create_promo_code("AUDIT7", "free_days", 7, 5)

        promo_service.apply_user_promo(app, 8, "AUDIT7")

        audit_entry = store.get_audit_log(limit=5)[0]
        self.assertEqual(audit_entry["type"], "promo_redeemed")
        self.assertEqual(audit_entry["promoCode"], "AUDIT7")
        self.assertEqual(audit_entry["promoType"], "free_days")
        self.assertEqual(audit_entry["userId"], 8)
        self.assertEqual(audit_entry["reason"], "promo_code")

    def test_free_days_promo_does_not_create_fake_payment(self):
        app, store = self.make_app()
        self.ensure_user(store, 9, "promo9")
        store.create_promo_code("NOPAY7", "free_days", 7, 5)

        promo_service.apply_user_promo(app, 9, "NOPAY7")

        self.assertEqual(store.get_payments(), [])
        self.assertEqual(store.get_user(9)["totalPaymentsCount"], 0)
        self.assertEqual(store.get_user(9)["totalSpentStars"], 0)


if __name__ == "__main__":
    unittest.main()

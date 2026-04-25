import ast
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from bot.services import referral_service
from store_py import create_store


class ReferralServiceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.store = create_store(str(Path(self.tempdir.name) / "db.json"))

    def _payment(self, user_id, charge_id):
        return {
            "userId": user_id,
            "paidAt": int(time.time() * 1000),
            "currency": "XTR",
            "totalAmount": 250,
            "telegramPaymentChargeId": charge_id,
            "invoicePayload": f"subscription:{user_id}",
        }

    def test_referral_service_imports_without_bot_app_cycle(self):
        path = Path("bot/services/referral_service.py")
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "bot.app")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "bot.app")

    def test_referral_code_generated_for_user(self):
        first = self.store.ensure_user({"id": 501, "first_name": "Ref", "username": "ref"})
        second = self.store.ensure_user({"id": 501, "first_name": "Ref", "username": "ref"})

        self.assertRegex(first["referralCode"], r"^[A-Z0-9]{6}$")
        self.assertEqual(first["referralCode"], second["referralCode"])

    def test_self_referral_forbidden(self):
        user = self.store.ensure_user({"id": 502, "first_name": "Self", "username": "self"})

        result = referral_service.apply_start_referral(
            SimpleNamespace(store=self.store),
            502,
            f"/start ref_{user['referralCode']}".split(None, 1)[1],
        )

        self.assertEqual(result["status"], "self_referral")
        self.assertIsNone(self.store.get_user(502)["referredBy"])

    def test_referral_saved_only_once(self):
        referrer_one = self.store.ensure_user({"id": 503, "first_name": "One", "username": "one"})
        referrer_two = self.store.ensure_user({"id": 504, "first_name": "Two", "username": "two"})
        referred = self.store.ensure_user({"id": 505, "first_name": "New", "username": "new"})

        first = referral_service.apply_start_referral(
            SimpleNamespace(store=self.store),
            referred["id"],
            f"ref_{referrer_one['referralCode']}",
        )
        second = referral_service.apply_start_referral(
            SimpleNamespace(store=self.store),
            referred["id"],
            f"ref_{referrer_two['referralCode']}",
        )

        self.assertEqual(first["status"], "attached")
        self.assertEqual(second["status"], "already_set")
        self.assertEqual(self.store.get_user(505)["referredBy"], 503)
        audit = [entry for entry in self.store.get_audit_log(limit=20) if entry.get("type") == "referral_attached"]
        self.assertEqual(len(audit), 1)

    def test_reward_granted_after_first_payment(self):
        referrer = self.store.ensure_user({"id": 506, "first_name": "Referrer", "username": "referrer"})
        referred = self.store.ensure_user({"id": 507, "first_name": "Referred", "username": "referred"})
        referral_service.apply_start_referral(
            SimpleNamespace(store=self.store),
            referred["id"],
            f"ref_{referrer['referralCode']}",
        )

        result = self.store.record_payment_and_activate_subscription(
            referred["id"],
            self._payment(referred["id"], "charge_referral_507"),
            self.store.get_settings(),
        )

        updated_referrer = self.store.get_user(referrer["id"])
        self.assertEqual(result["status"], "processed")
        self.assertIsNotNone(updated_referrer["subscriptionUntil"])
        self.assertEqual(len(updated_referrer["referralRewards"]), 1)
        self.assertEqual(updated_referrer["referralRewards"][0]["referredUserId"], 507)
        audit = self.store.get_audit_log(limit=20)
        self.assertTrue(any(entry.get("type") == "referral_reward_granted" for entry in audit))

    def test_duplicate_payment_does_not_grant_reward_twice(self):
        referrer = self.store.ensure_user({"id": 508, "first_name": "Referrer", "username": "referrer"})
        referred = self.store.ensure_user({"id": 509, "first_name": "Referred", "username": "referred"})
        referral_service.apply_start_referral(
            SimpleNamespace(store=self.store),
            referred["id"],
            f"ref_{referrer['referralCode']}",
        )

        first = self.store.record_payment_and_activate_subscription(
            referred["id"],
            self._payment(referred["id"], "charge_referral_509"),
            self.store.get_settings(),
        )
        referrer_after_first = self.store.get_user(referrer["id"])
        second = self.store.record_payment_and_activate_subscription(
            referred["id"],
            self._payment(referred["id"], "charge_referral_509"),
            self.store.get_settings(),
        )
        referrer_after_second = self.store.get_user(referrer["id"])

        self.assertEqual(first["status"], "processed")
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(len(referrer_after_first["referralRewards"]), 1)
        self.assertEqual(len(referrer_after_second["referralRewards"]), 1)
        self.assertEqual(referrer_after_first["subscriptionUntil"], referrer_after_second["subscriptionUntil"])


if __name__ == "__main__":
    unittest.main()

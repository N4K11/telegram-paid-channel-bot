import json
import os
import tempfile
import unittest
from unittest.mock import patch

from store_py import create_store
from utils_py import add_days


class StorePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db_path = os.path.join(self.tempdir.name, "db.json")

    def make_store(self):
        return create_store(self.db_path)

    def write_raw_state(self, payload):
        with open(self.db_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    def test_store_initializes_missing_db(self):
        store = self.make_store()
        state = store.get_state()

        self.assertTrue(os.path.exists(self.db_path))
        self.assertIn("meta", state)
        self.assertIn("settings", state)
        self.assertIn("users", state)
        self.assertIn("payments", state)
        self.assertIn("auditLog", state)
        self.assertIn("messageTemplates", state["settings"])
        self.assertIn("paymentReceived", state["settings"]["messageTemplates"])

    def test_corrupt_db_raises_predictable_error(self):
        with open(self.db_path, "w", encoding="utf-8") as file:
            file.write("{")

        with self.assertRaises(RuntimeError) as error:
            self.make_store()

        self.assertIn("Invalid JSON in store file", str(error.exception))

    def test_partial_state_is_migrated_without_data_loss(self):
        partial_state = {
            "settings": {
                "subscriptionPriceStars": 123,
                "messageTemplates": {
                    "paymentReceived": "custom template",
                },
            },
            "users": {
                "1": {
                    "id": 1,
                    "firstName": "Ivan",
                }
            },
            "payments": {
                "charge_1": {
                    "telegramPaymentChargeId": "charge_1",
                    "userId": 1,
                    "totalAmount": 123,
                    "paidAt": 111,
                }
            },
        }
        self.write_raw_state(partial_state)

        store = self.make_store()
        state = store.get_state()

        self.assertEqual(state["settings"]["subscriptionPriceStars"], 123)
        self.assertEqual(state["settings"]["messageTemplates"]["paymentReceived"], "custom template")
        self.assertEqual(state["users"]["1"]["firstName"], "Ivan")
        self.assertIn("warningDays", state["settings"])
        self.assertIn("meta", state)
        self.assertIn("auditLog", state)
        self.assertIn("paymentReceived", state["settings"]["messageTemplates"])
        self.assertIn("charge_1", state["payments"])

    def test_update_settings_persists(self):
        store = self.make_store()
        store.update_settings({"subscriptionPriceStars": 777, "warningDays": 5})

        reloaded = self.make_store()
        settings = reloaded.get_settings()
        self.assertEqual(settings["subscriptionPriceStars"], 777)
        self.assertEqual(settings["warningDays"], 5)

    def test_message_templates_persist(self):
        store = self.make_store()
        store.update_settings(
            {
                "messageTemplates": {
                    "paymentReceived": "Р В РЎСљР В РЎвЂўР В Р вЂ Р РЋРІР‚в„–Р В РІвЂћвЂ“ Р РЋРІвЂљВ¬Р В Р’В°Р В Р’В±Р В Р’В»Р В РЎвЂўР В Р вЂ¦",
                }
            }
        )

        reloaded = self.make_store()
        templates = reloaded.get_settings()["messageTemplates"]
        self.assertEqual(templates["paymentReceived"], "Р В РЎСљР В РЎвЂўР В Р вЂ Р РЋРІР‚в„–Р В РІвЂћвЂ“ Р РЋРІвЂљВ¬Р В Р’В°Р В Р’В±Р В Р’В»Р В РЎвЂўР В Р вЂ¦")
        self.assertIn("subscriptionExpired", templates)

    def test_ensure_user_is_idempotent(self):
        store = self.make_store()

        first = store.ensure_user({"id": 1, "first_name": "Ivan", "username": "ivan"})
        second = store.ensure_user({"id": 1, "first_name": "Ivan", "last_name": "Petrov"})

        self.assertEqual(len(store.list_users()), 1)
        self.assertEqual(first["id"], 1)
        self.assertEqual(second["id"], 1)
        self.assertEqual(second["firstName"], "Ivan")
        self.assertEqual(second["lastName"], "Petrov")
        self.assertEqual(second["username"], "ivan")

    def test_update_user_fields_persists(self):
        store = self.make_store()
        store.ensure_user({"id": 2, "first_name": "Petr"})
        store.update_user_fields(
            2,
            {
                "balanceStars": 50,
                "subscriptionUntil": 123456789,
                "channelMemberStatus": "member",
            },
        )

        reloaded = self.make_store()
        user = reloaded.get_user(2)
        self.assertEqual(user["balanceStars"], 50)
        self.assertEqual(user["subscriptionUntil"], 123456789)
        self.assertEqual(user["channelMemberStatus"], "member")

    def test_record_payment_is_idempotent(self):
        store = self.make_store()
        store.ensure_user({"id": 3, "first_name": "Mila"})
        payment = {
            "telegramPaymentChargeId": "charge_3",
            "userId": 3,
            "totalAmount": 250,
            "paidAt": 111111,
        }

        store.record_payment(payment)
        store.record_payment(payment)

        user = store.get_user(3)
        payments = store.get_payments()
        self.assertEqual(len(payments), 1)
        self.assertEqual(user["totalSpentStars"], 250)
        self.assertEqual(user["totalPaymentsCount"], 1)
        self.assertEqual(user["lastPaymentAt"], 111111)

    def test_record_payment_and_activate_subscription_single_transaction_success(self):
        fixed_now_ms = 1_700_000_000_000
        store = self.make_store()
        store.ensure_user({"id": 21, "first_name": "AtomicPay"})
        settings = store.get_settings()
        payment = {
            "telegramPaymentChargeId": "charge_atomic_success",
            "userId": 21,
            "totalAmount": 250,
            "paidAt": fixed_now_ms,
            "invoicePayload": "subscription:21",
            "currency": "XTR",
        }

        with patch("store_py.time.time", return_value=fixed_now_ms / 1000):
            result = store.record_payment_and_activate_subscription(21, payment, settings)

        reloaded = self.make_store()
        user = reloaded.get_user(21)
        self.assertEqual(result["status"], "processed")
        self.assertTrue(reloaded.has_payment("charge_atomic_success"))
        self.assertEqual(user["totalSpentStars"], 250)
        self.assertEqual(user["totalPaymentsCount"], 1)
        self.assertEqual(user["lastPaymentAt"], fixed_now_ms)
        self.assertEqual(user["subscriptionUntil"], add_days(fixed_now_ms, settings["subscriptionDurationDays"]))
        self.assertEqual(user["lastAccessGrantedAt"], fixed_now_ms)

    def test_record_payment_and_activate_subscription_duplicate_is_idempotent(self):
        fixed_now_ms = 1_700_000_000_000
        store = self.make_store()
        store.ensure_user({"id": 22, "first_name": "AtomicDuplicate"})
        settings = store.get_settings()
        payment = {
            "telegramPaymentChargeId": "charge_atomic_duplicate",
            "userId": 22,
            "totalAmount": 250,
            "paidAt": fixed_now_ms,
            "invoicePayload": "subscription:22",
            "currency": "XTR",
        }

        with patch("store_py.time.time", return_value=fixed_now_ms / 1000):
            first = store.record_payment_and_activate_subscription(22, payment, settings)
            first_user = store.get_user(22)
            second = store.record_payment_and_activate_subscription(22, payment, settings)
            second_user = store.get_user(22)

        self.assertEqual(first["status"], "processed")
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(first_user["subscriptionUntil"], second_user["subscriptionUntil"])
        self.assertEqual(second_user["totalSpentStars"], 250)
        self.assertEqual(second_user["totalPaymentsCount"], 1)
        self.assertEqual(len(store.get_payments()), 1)

    def test_record_payment_and_activate_subscription_rolls_back_on_failed_save(self):
        fixed_now_ms = 1_700_000_000_000
        store = self.make_store()
        store.ensure_user({"id": 23, "first_name": "AtomicRollback"})
        original_user = store.get_user(23)
        settings = store.get_settings()
        payment = {
            "telegramPaymentChargeId": "charge_atomic_rollback",
            "userId": 23,
            "totalAmount": 250,
            "paidAt": fixed_now_ms,
            "invoicePayload": "subscription:23",
            "currency": "XTR",
        }
        with open(self.db_path, "r", encoding="utf-8") as file:
            original_disk = json.load(file)

        with patch("store_py.time.time", return_value=fixed_now_ms / 1000), \
             patch.object(store, "_save_unlocked", side_effect=OSError("save failed")):
            with self.assertRaises(OSError):
                store.record_payment_and_activate_subscription(23, payment, settings)

        self.assertFalse(store.has_payment("charge_atomic_rollback"))
        self.assertEqual(store.get_user(23), original_user)
        with open(self.db_path, "r", encoding="utf-8") as file:
            current_on_disk = json.load(file)
        self.assertEqual(current_on_disk, original_disk)

    def test_record_payment_and_activate_subscription_legacy_duplicate_policy(self):
        fixed_now_ms = 1_700_000_000_000
        store = self.make_store()
        store.ensure_user({"id": 24, "first_name": "LegacyDuplicate"})
        settings = store.get_settings()
        payment = {
            "telegramPaymentChargeId": "charge_legacy_duplicate",
            "userId": 24,
            "totalAmount": 250,
            "paidAt": fixed_now_ms,
            "invoicePayload": "subscription:24",
            "currency": "XTR",
        }

        store.record_payment(payment)
        user_before = store.get_user(24)

        with patch("store_py.time.time", return_value=fixed_now_ms / 1000):
            result = store.record_payment_and_activate_subscription(24, payment, settings)

        user_after = store.get_user(24)
        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(user_after["subscriptionUntil"], user_before["subscriptionUntil"])
        self.assertEqual(user_after["totalSpentStars"], user_before["totalSpentStars"])
        self.assertEqual(user_after["totalPaymentsCount"], user_before["totalPaymentsCount"])

    def test_payment_diagnostics_read_only(self):
        fixed_now_ms = 1_700_000_000_000
        store = self.make_store()
        store.ensure_user({"id": 25, "first_name": "Diag"})
        settings = store.get_settings()
        payment = {
            "telegramPaymentChargeId": "charge_diag",
            "userId": 25,
            "totalAmount": 250,
            "paidAt": fixed_now_ms,
            "invoicePayload": "subscription:25",
            "currency": "XTR",
        }
        with patch("store_py.time.time", return_value=fixed_now_ms / 1000):
            store.record_payment_and_activate_subscription(25, payment, settings)

        before = store.get_state()
        diagnostics = store.get_user_payment_diagnostics(25, current_time_ms=fixed_now_ms)
        after = store.get_state()

        self.assertEqual(before, after)
        self.assertEqual(diagnostics["userId"], 25)
        self.assertTrue(diagnostics["subscriptionActive"])
        self.assertEqual(diagnostics["totalPaymentsCount"], 1)
        self.assertEqual(len(diagnostics["recentPayments"]), 1)

    def test_payment_diagnostics_detects_duplicate_charge_ids(self):
        fixed_now_ms = 1_700_000_000_000
        self.write_raw_state(
            {
                "users": {
                    "26": {
                        "id": 26,
                        "firstName": "Dup",
                        "totalSpentStars": 500,
                        "totalPaymentsCount": 2,
                        "subscriptionUntil": fixed_now_ms + 1_000,
                    }
                },
                "payments": {
                    "key_a": {
                        "telegramPaymentChargeId": "dup_charge",
                        "userId": 26,
                        "totalAmount": 250,
                        "paidAt": fixed_now_ms,
                        "invoicePayload": "subscription:26",
                        "currency": "XTR",
                    },
                    "key_b": {
                        "telegramPaymentChargeId": "dup_charge",
                        "userId": 26,
                        "totalAmount": 250,
                        "paidAt": fixed_now_ms - 1,
                        "invoicePayload": "subscription:26",
                        "currency": "XTR",
                    },
                },
            }
        )
        store = self.make_store()

        diagnostics = store.get_user_payment_diagnostics(26, current_time_ms=fixed_now_ms)

        self.assertEqual(diagnostics["duplicateChargeIds"], ["dup_charge"])
        self.assertTrue(any("повторяющиеся telegramPaymentChargeId" in warning for warning in diagnostics["warnings"]))

    def test_payment_diagnostics_detects_payment_without_active_subscription(self):
        fixed_now_ms = 1_700_000_000_000
        store = self.make_store()
        store.ensure_user({"id": 27, "first_name": "NoActive"})
        store.record_payment(
            {
                "telegramPaymentChargeId": "charge_no_active",
                "userId": 27,
                "totalAmount": 250,
                "paidAt": fixed_now_ms,
                "invoicePayload": "subscription:27",
                "currency": "XTR",
            }
        )

        diagnostics = store.get_user_payment_diagnostics(27, current_time_ms=fixed_now_ms)

        self.assertFalse(diagnostics["subscriptionActive"])
        self.assertTrue(any("активной подписки" in warning for warning in diagnostics["warnings"]))

    def test_manual_recovery_grants_access_without_changing_payment_totals(self):
        fixed_now_ms = 1_700_000_000_000
        store = self.make_store()
        store.ensure_user({"id": 28, "first_name": "ManualRecover"})
        store.record_payment(
            {
                "telegramPaymentChargeId": "charge_manual",
                "userId": 28,
                "totalAmount": 250,
                "paidAt": fixed_now_ms,
                "invoicePayload": "subscription:28",
                "currency": "XTR",
            }
        )
        before_user = store.get_user(28)

        with patch("store_py.time.time", return_value=fixed_now_ms / 1000):
            recovered = store.manual_payment_recovery(999, 28, 30, "manual_verification")

        audit = store.get_audit_log(limit=5)
        self.assertEqual(recovered["totalSpentStars"], before_user["totalSpentStars"])
        self.assertEqual(recovered["totalPaymentsCount"], before_user["totalPaymentsCount"])
        self.assertEqual(recovered["subscriptionUntil"], add_days(fixed_now_ms, 30))
        self.assertEqual(audit[0]["type"], "manual_payment_recovery")
        self.assertEqual(audit[0]["adminId"], 999)
        self.assertEqual(audit[0]["reason"], "manual_verification")

    def test_manual_recovery_does_not_create_fake_payment(self):
        fixed_now_ms = 1_700_000_000_000
        store = self.make_store()
        store.ensure_user({"id": 29, "first_name": "NoFakePayment"})
        initial_payments = store.get_payments()

        with patch("store_py.time.time", return_value=fixed_now_ms / 1000):
            store.manual_payment_recovery(1001, 29, 15, "verified_off_platform")

        self.assertEqual(store.get_payments(), initial_payments)
        self.assertEqual(store.get_user(29)["totalSpentStars"], 0)
        self.assertEqual(store.get_user(29)["totalPaymentsCount"], 0)

    def test_list_payment_anomalies_read_only(self):
        fixed_now_ms = 1_700_000_000_000
        store = self.make_store()
        store.ensure_user({"id": 30, "first_name": "CleanUser", "username": "clean"})
        store.ensure_user({"id": 31, "first_name": "SuspiciousUser", "username": "suspicious"})
        store.record_payment(
            {
                "telegramPaymentChargeId": "charge_anomaly_31",
                "userId": 31,
                "totalAmount": 250,
                "paidAt": fixed_now_ms,
                "invoicePayload": "subscription:31",
                "currency": "XTR",
            }
        )

        before = store.get_state()
        anomalies = store.list_payment_anomalies(limit=20, current_time_ms=fixed_now_ms)
        after = store.get_state()

        self.assertEqual(before, after)
        self.assertEqual([item["userId"] for item in anomalies], [31])
        self.assertEqual(anomalies[0]["displayName"], "SuspiciousUser")

    def test_list_payment_anomalies_detects_duplicate_charge_ids(self):
        fixed_now_ms = 1_700_000_000_000
        self.write_raw_state(
            {
                "users": {
                    "32": {
                        "id": 32,
                        "firstName": "DupList",
                        "totalSpentStars": 500,
                        "totalPaymentsCount": 2,
                        "subscriptionUntil": fixed_now_ms + 1_000,
                    }
                },
                "payments": {
                    "dup_key_a": {
                        "telegramPaymentChargeId": "dup_list_charge",
                        "userId": 32,
                        "totalAmount": 250,
                        "paidAt": fixed_now_ms,
                        "invoicePayload": "subscription:32",
                        "currency": "XTR",
                    },
                    "dup_key_b": {
                        "telegramPaymentChargeId": "dup_list_charge",
                        "userId": 32,
                        "totalAmount": 250,
                        "paidAt": fixed_now_ms - 1,
                        "invoicePayload": "subscription:32",
                        "currency": "XTR",
                    },
                },
            }
        )
        store = self.make_store()

        anomalies = store.list_payment_anomalies(limit=20, current_time_ms=fixed_now_ms)

        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["userId"], 32)
        self.assertTrue(any("telegramPaymentChargeId" in warning for warning in anomalies[0]["warnings"]))

    def test_list_payment_anomalies_detects_totals_mismatch(self):
        fixed_now_ms = 1_700_000_000_000
        self.write_raw_state(
            {
                "users": {
                    "33": {
                        "id": 33,
                        "firstName": "Mismatch",
                        "totalSpentStars": 999,
                        "totalPaymentsCount": 5,
                        "subscriptionUntil": fixed_now_ms + 5_000,
                        "lastPaymentAt": fixed_now_ms,
                    }
                },
                "payments": {
                    "charge_33": {
                        "telegramPaymentChargeId": "charge_33",
                        "userId": 33,
                        "totalAmount": 250,
                        "paidAt": fixed_now_ms,
                        "invoicePayload": "subscription:33",
                        "currency": "XTR",
                    }
                },
            }
        )
        store = self.make_store()

        anomalies = store.list_payment_anomalies(limit=20, current_time_ms=fixed_now_ms)

        self.assertEqual(len(anomalies), 1)
        self.assertTrue(any("totalPaymentsCount" in warning for warning in anomalies[0]["warnings"]))
        self.assertTrue(any("totalSpentStars" in warning for warning in anomalies[0]["warnings"]))

    def test_list_payment_anomalies_respects_limit(self):
        fixed_now_ms = 1_700_000_000_000
        store = self.make_store()

        for user_id, offset in ((34, 3000), (35, 2000), (36, 1000)):
            store.ensure_user({"id": user_id, "first_name": f"User{user_id}"})
            store.record_payment(
                {
                    "telegramPaymentChargeId": f"charge_{user_id}",
                    "userId": user_id,
                    "totalAmount": 250,
                    "paidAt": fixed_now_ms + offset,
                    "invoicePayload": f"subscription:{user_id}",
                    "currency": "XTR",
                }
            )

        anomalies = store.list_payment_anomalies(limit=2, current_time_ms=fixed_now_ms)

        self.assertEqual(len(anomalies), 2)
        self.assertEqual([item["userId"] for item in anomalies], [34, 35])

    def test_list_payment_anomalies_empty_when_clean(self):
        store = self.make_store()
        store.ensure_user({"id": 37, "first_name": "CleanOnly"})

        anomalies = store.list_payment_anomalies(limit=20)

        self.assertEqual(anomalies, [])
    def test_activate_subscription_extends_existing_active_subscription(self):
        fixed_now_ms = 1_700_000_000_000
        existing_until = fixed_now_ms + 5 * 24 * 60 * 60 * 1000
        store = self.make_store()
        settings = store.get_settings()
        payment = {
            "telegramPaymentChargeId": "charge_4",
            "userId": 4,
            "totalAmount": 250,
            "paidAt": fixed_now_ms,
        }

        store.ensure_user({"id": 4, "first_name": "Oleg"})
        store.update_user_fields(4, {"subscriptionUntil": existing_until})

        with patch("store_py.time.time", return_value=fixed_now_ms / 1000):
            user = store.activate_subscription_from_payment(4, payment, settings)

        self.assertEqual(user["subscriptionUntil"], add_days(existing_until, settings["subscriptionDurationDays"]))

    def test_activate_subscription_from_expired_starts_from_now(self):
        fixed_now_ms = 1_700_000_000_000
        expired_until = fixed_now_ms - 24 * 60 * 60 * 1000
        store = self.make_store()
        settings = store.get_settings()
        payment = {
            "telegramPaymentChargeId": "charge_5",
            "userId": 5,
            "totalAmount": 250,
            "paidAt": fixed_now_ms,
        }

        store.ensure_user({"id": 5, "first_name": "Anna"})
        store.update_user_fields(5, {"subscriptionUntil": expired_until})

        with patch("store_py.time.time", return_value=fixed_now_ms / 1000):
            user = store.activate_subscription_from_payment(5, payment, settings)

        self.assertEqual(user["subscriptionUntil"], add_days(fixed_now_ms, settings["subscriptionDurationDays"]))

    def test_balance_adjustment(self):
        store = self.make_store()
        store.ensure_user({"id": 6, "first_name": "Roma"})

        store.adjust_balance(6, 80)
        store.adjust_balance(6, -30)
        user = store.adjust_balance(6, -1000)

        self.assertEqual(user["balanceStars"], 0)
        self.assertEqual(self.make_store().get_user(6)["balanceStars"], 0)

    def test_purchase_with_balance_is_single_transaction(self):
        fixed_now_ms = 1_700_000_000_000
        store = self.make_store()
        store.ensure_user({"id": 14, "first_name": "BalanceBuyer"})
        store.adjust_balance(14, 500)
        settings = store.get_settings()

        with patch("store_py.time.time", return_value=fixed_now_ms / 1000):
            result = store.purchase_with_balance(14, settings)

        user = store.get_user(14)
        audit = store.get_audit_log(limit=5)
        self.assertTrue(result["ok"])
        self.assertEqual(user["balanceStars"], 500 - settings["subscriptionPriceStars"])
        self.assertEqual(user["subscriptionUntil"], add_days(fixed_now_ms, settings["subscriptionDurationDays"]))
        self.assertEqual(user["lastAccessGrantedAt"], fixed_now_ms)
        self.assertEqual(audit[0]["type"], "grant_subscription")
        self.assertEqual(audit[0]["reason"], "balance_purchase")

    def test_purchase_with_balance_can_repeat_when_balance_is_sufficient(self):
        fixed_now_ms = 1_700_000_000_000
        store = self.make_store()
        store.ensure_user({"id": 20, "first_name": "RepeatBuyer"})
        store.adjust_balance(20, 1000)
        settings = store.get_settings()

        with patch("store_py.time.time", return_value=fixed_now_ms / 1000):
            first = store.purchase_with_balance(20, settings)
            second = store.purchase_with_balance(20, settings)

        user = store.get_user(20)
        expected_until = add_days(add_days(fixed_now_ms, settings["subscriptionDurationDays"]), settings["subscriptionDurationDays"])
        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(user["balanceStars"], 1000 - settings["subscriptionPriceStars"] * 2)
        self.assertEqual(user["subscriptionUntil"], expected_until)

    def test_purchase_with_balance_rolls_back_all_changes_on_failed_save(self):
        fixed_now_ms = 1_700_000_000_000
        store = self.make_store()
        store.ensure_user({"id": 15, "first_name": "RollbackBuyer"})
        store.adjust_balance(15, 500)
        settings = store.get_settings()
        original_user = store.get_user(15)
        original_audit = store.get_audit_log(limit=20)
        with open(self.db_path, "r", encoding="utf-8") as file:
            original_disk = json.load(file)

        with patch("store_py.time.time", return_value=fixed_now_ms / 1000), \
             patch("store_py.os.replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                store.purchase_with_balance(15, settings)

        self.assertEqual(store.get_user(15), original_user)
        self.assertEqual(store.get_audit_log(limit=20), original_audit)
        with open(self.db_path, "r", encoding="utf-8") as file:
            current_on_disk = json.load(file)
        self.assertEqual(current_on_disk, original_disk)
        self.assertFalse(os.path.exists(f"{self.db_path}.tmp"))

    def test_purchase_with_balance_insufficient_balance_no_partial_change(self):
        store = self.make_store()
        store.ensure_user({"id": 16, "first_name": "LowBalance"})
        settings = store.get_settings()
        original_user = store.get_user(16)
        original_audit = store.get_audit_log(limit=20)

        result = store.purchase_with_balance(16, settings)

        self.assertEqual(result, {"ok": False, "reason": "not_enough_balance"})
        self.assertEqual(store.get_user(16), original_user)
        self.assertEqual(store.get_audit_log(limit=20), original_audit)

    def test_pending_join_request_lifecycle(self):
        store = self.make_store()
        store.ensure_user({"id": 7, "first_name": "Kirill"})

        store.set_user_pending_join_request(7, {"chatId": -100, "requestedAt": 123})
        self.assertEqual(store.get_user(7)["pendingJoinRequest"]["chatId"], -100)

        store.clear_user_pending_join_request(7)
        self.assertIsNone(store.get_user(7)["pendingJoinRequest"])

    def test_channel_member_status_persists(self):
        store = self.make_store()
        store.ensure_user({"id": 8, "first_name": "Nina"})
        store.set_user_channel_member_status(8, "left")

        self.assertEqual(self.make_store().get_user(8)["channelMemberStatus"], "left")

    def test_dashboard_stats_basic(self):
        current_time_ms = 1_700_000_000_000
        store = self.make_store()
        store.ensure_user({"id": 9, "first_name": "A"})
        store.ensure_user({"id": 10, "first_name": "B"})
        store.ensure_user({"id": 11, "first_name": "C"})
        store.update_user_fields(9, {"subscriptionUntil": current_time_ms + 10_000, "channelMemberStatus": "member"})
        store.update_user_fields(10, {"subscriptionUntil": current_time_ms - 10_000})
        store.update_user_fields(11, {"pendingJoinRequest": {"chatId": -100, "requestedAt": current_time_ms}})
        store.record_payment(
            {
                "telegramPaymentChargeId": "charge_stats",
                "userId": 9,
                "totalAmount": 250,
                "paidAt": current_time_ms,
            }
        )
        store.adjust_balance(11, 40)

        stats = store.get_dashboard_stats(current_time_ms=current_time_ms)

        self.assertEqual(stats["totalUsers"], 3)
        self.assertEqual(stats["activeSubscriptions"], 1)
        self.assertEqual(stats["expiredSubscriptions"], 1)
        self.assertEqual(stats["pendingJoinRequests"], 1)
        self.assertEqual(stats["revenueStars"], 250)
        self.assertEqual(stats["totalBalanceStars"], 40)
        self.assertEqual(stats["channelMembers"], 1)

    def test_activate_subscription_from_payment_single_transaction(self):
        fixed_now_ms = 1_700_000_000_000
        store = self.make_store()
        store.ensure_user({"id": 17, "first_name": "PaymentSub"})
        store.update_user_fields(
            17,
            {
                "subscriptionUntil": fixed_now_ms - 1_000,
                "lastWarningAt": 123,
                "lastAccessGrantedAt": None,
            },
        )
        settings = store.get_settings()
        payment = {
            "telegramPaymentChargeId": "charge_activate_single",
            "userId": 17,
            "totalAmount": 250,
            "paidAt": fixed_now_ms,
        }

        with patch("store_py.time.time", return_value=fixed_now_ms / 1000):
            user = store.activate_subscription_from_payment(17, payment, settings)

        self.assertEqual(user["subscriptionUntil"], add_days(fixed_now_ms, settings["subscriptionDurationDays"]))
        self.assertIsNone(user["lastWarningAt"])
        self.assertEqual(user["lastAccessGrantedAt"], fixed_now_ms)

    def test_grant_subscription_days_rolls_back_on_failed_save(self):
        fixed_now_ms = 1_700_000_000_000
        store = self.make_store()
        store.ensure_user({"id": 18, "first_name": "GrantRollback"})
        original_user = store.get_user(18)
        original_audit = store.get_audit_log(limit=20)

        with patch("store_py.time.time", return_value=fixed_now_ms / 1000), \
             patch.object(store, "_save_unlocked", side_effect=OSError("save failed")):
            with self.assertRaises(OSError):
                store.grant_subscription_days(18, 30)

        self.assertEqual(store.get_user(18), original_user)
        self.assertEqual(store.get_audit_log(limit=20), original_audit)

    def test_revoke_subscription_rolls_back_on_failed_save(self):
        fixed_now_ms = 1_700_000_000_000
        store = self.make_store()
        store.ensure_user({"id": 19, "first_name": "RevokeRollback"})
        store.update_user_fields(19, {"subscriptionUntil": fixed_now_ms + 10_000})
        original_user = store.get_user(19)
        original_audit = store.get_audit_log(limit=20)

        with patch("store_py.time.time", return_value=fixed_now_ms / 1000), \
             patch.object(store, "_save_unlocked", side_effect=OSError("save failed")):
            with self.assertRaises(OSError):
                store.revoke_subscription(19)

        self.assertEqual(store.get_user(19), original_user)
        self.assertEqual(store.get_audit_log(limit=20), original_audit)

    def test_audit_log_append(self):
        store = self.make_store()

        store.add_audit_log({"type": "first", "value": 1})
        store.add_audit_log({"type": "second", "value": 2})

        entries = store.get_audit_log(limit=2)
        reloaded_entries = self.make_store().get_audit_log(limit=2)
        self.assertEqual(entries[0]["type"], "second")
        self.assertEqual(entries[1]["type"], "first")
        self.assertEqual(reloaded_entries[0]["type"], "second")
        self.assertEqual(reloaded_entries[1]["type"], "first")

    def test_failed_save_rolls_back_update_settings_in_memory(self):
        store = self.make_store()
        original_settings = store.get_settings()

        with patch.object(store, "_save_unlocked", side_effect=OSError("save failed")):
            with self.assertRaises(OSError):
                store.update_settings({"subscriptionPriceStars": 999})

        self.assertEqual(store.get_settings(), original_settings)

    def test_failed_save_rolls_back_user_update_in_memory(self):
        store = self.make_store()
        store.ensure_user({"id": 12, "first_name": "Rollback"})
        original_user = store.get_user(12)

        with patch.object(store, "_save_unlocked", side_effect=OSError("save failed")):
            with self.assertRaises(OSError):
                store.update_user_fields(12, {"balanceStars": 500, "channelMemberStatus": "member"})

        self.assertEqual(store.get_user(12), original_user)

    def test_failed_save_rolls_back_record_payment_in_memory(self):
        store = self.make_store()
        store.ensure_user({"id": 13, "first_name": "Payment"})
        original_user = store.get_user(13)
        payment = {
            "telegramPaymentChargeId": "charge_rollback",
            "userId": 13,
            "totalAmount": 250,
            "paidAt": 222222,
        }

        with patch.object(store, "_save_unlocked", side_effect=OSError("save failed")):
            with self.assertRaises(OSError):
                store.record_payment(payment)

        self.assertFalse(store.has_payment("charge_rollback"))
        self.assertEqual(store.get_user(13), original_user)

    def test_failed_save_rolls_back_audit_log_in_memory(self):
        store = self.make_store()
        store.add_audit_log({"type": "baseline", "value": 1})
        original_audit = store.get_audit_log(limit=10)

        with patch.object(store, "_save_unlocked", side_effect=OSError("save failed")):
            with self.assertRaises(OSError):
                store.add_audit_log({"type": "should_rollback", "value": 2})

        self.assertEqual(store.get_audit_log(limit=10), original_audit)

    def test_failed_save_keeps_disk_file_valid(self):
        store = self.make_store()
        with open(self.db_path, "r", encoding="utf-8") as file:
            original_on_disk = json.load(file)

        with patch("store_py.os.replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                store.update_settings({"subscriptionPriceStars": 999})

        with open(self.db_path, "r", encoding="utf-8") as file:
            current_on_disk = json.load(file)

        self.assertEqual(current_on_disk, original_on_disk)
        self.assertEqual(
            store.get_settings()["subscriptionPriceStars"],
            original_on_disk["settings"]["subscriptionPriceStars"],
        )
        self.assertFalse(os.path.exists(f"{self.db_path}.tmp"))


if __name__ == "__main__":
    unittest.main()



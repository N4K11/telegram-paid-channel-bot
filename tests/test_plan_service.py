import ast
import unittest
from pathlib import Path

from bot.services import plan_service


class PlanServiceTests(unittest.TestCase):
    def test_plan_service_imports_without_bot_app_cycle(self):
        tree = ast.parse(Path("bot/services/plan_service.py").read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "bot.app")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "bot.app")

    def test_fallback_plan_uses_legacy_settings(self):
        settings = {
            "subscriptionName": "Base",
            "subscriptionPriceStars": 250,
            "subscriptionDurationDays": 30,
        }

        plans = plan_service.get_enabled_plans(settings)

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["id"], "default")
        self.assertEqual(plans[0]["priceStars"], 250)
        self.assertEqual(plans[0]["durationDays"], 30)
        self.assertTrue(plans[0]["isFallback"])

    def test_old_and_new_payload_parse(self):
        self.assertEqual(
            plan_service.parse_plan_payload("subscription:123"),
            {"userId": 123, "planId": None},
        )
        self.assertEqual(
            plan_service.parse_plan_payload("subscription:123:week"),
            {"userId": 123, "planId": "week"},
        )
        self.assertEqual(plan_service.build_plan_payload(123), "subscription:123")
        self.assertEqual(plan_service.build_plan_payload(123, "week"), "subscription:123:week")
        self.assertIsNone(plan_service.parse_plan_payload("subscription:abc"))
        self.assertIsNone(plan_service.parse_plan_payload("subscription:123:"))
        self.assertIsNone(plan_service.parse_plan_payload("other:123"))

    def test_disabled_plan_not_returned_as_enabled(self):
        settings = {
            "subscriptionName": "Base",
            "subscriptionPriceStars": 250,
            "subscriptionDurationDays": 30,
            "plans": [
                {"id": "day", "title": "1 день", "priceStars": 20, "durationDays": 1, "enabled": True},
                {"id": "week", "title": "7 дней", "priceStars": 70, "durationDays": 7, "enabled": False},
            ],
        }

        enabled = plan_service.get_enabled_plans(settings)

        self.assertEqual([plan["id"] for plan in enabled], ["day"])
        self.assertIsNone(plan_service.get_plan(settings, "week"))

    def test_apply_plan_to_settings_uses_plan_values(self):
        settings = {
            "subscriptionPriceStars": 250,
            "subscriptionDurationDays": 30,
        }
        plan = {
            "id": "week",
            "title": "7 дней",
            "priceStars": 70,
            "durationDays": 7,
            "enabled": True,
            "isLifetime": False,
        }

        effective = plan_service.apply_plan_to_settings(settings, plan)

        self.assertEqual(effective["subscriptionPriceStars"], 70)
        self.assertEqual(effective["subscriptionDurationDays"], 7)
        self.assertFalse(effective["isLifetimePlan"])
        self.assertEqual(effective["selectedPlanId"], "week")

    def test_lifetime_plan_normalizes_and_marks_settings(self):
        settings = {
            "subscriptionName": "Base",
            "subscriptionPriceStars": 250,
            "subscriptionDurationDays": 30,
            "plans": [
                {"id": "life", "title": "Навсегда", "priceStars": 5000, "durationDays": 0, "enabled": True},
            ],
        }

        plan = plan_service.get_plan(settings, "life")
        effective = plan_service.apply_plan_to_settings(settings, plan)

        self.assertTrue(plan["isLifetime"])
        self.assertTrue(effective["isLifetimePlan"])
        self.assertEqual(effective["subscriptionDurationDays"], plan_service.LIFETIME_SENTINEL_DAYS)


if __name__ == "__main__":
    unittest.main()
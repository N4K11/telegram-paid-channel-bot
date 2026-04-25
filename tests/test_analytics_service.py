import ast
import importlib
import tempfile
import unittest
from pathlib import Path

from bot.app import SubscriptionBotApp
from config import Config
from store_py import create_store
from utils_py import parse_datetime_local_value


class AnalyticsServiceTests(unittest.TestCase):
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

    def make_app(self):
        config = self.make_config()
        store = create_store(config.data_file_path)
        app = SubscriptionBotApp(config, store)
        app._bootstrap()
        return app

    def ensure_payment(self, app, user_id, charge_id, amount, paid_at):
        app.store.ensure_user({"id": user_id, "first_name": f"User{user_id}", "username": f"user{user_id}"})
        return app.store.record_payment(
            {
                "telegramPaymentChargeId": charge_id,
                "userId": user_id,
                "totalAmount": amount,
                "paidAt": paid_at,
                "invoicePayload": f"subscription:{user_id}",
                "currency": "XTR",
            }
        )

    def test_analytics_service_imports_without_bot_app_cycle(self):
        module = importlib.import_module("bot.services.analytics_service")
        self.assertTrue(hasattr(module, "get_analytics_snapshot"))
        self.assertTrue(hasattr(module, "format_stats_summary"))
        self.assertTrue(hasattr(module, "format_revenue_report"))
        self.assertTrue(hasattr(module, "format_activity_report"))

        tree = ast.parse(
            Path("bot/services/analytics_service.py").read_text(encoding="utf-8-sig"),
            filename="bot/services/analytics_service.py",
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "bot.app")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "bot.app")

    def test_analytics_read_only(self):
        from bot.services import analytics_service

        app = self.make_app()
        now_ms = parse_datetime_local_value("2026-04-08T12:00", app.config.app_timezone)
        self.ensure_payment(app, 1, "charge_read_only", 250, now_ms - 1000)
        before = app.store.get_state()

        snapshot = analytics_service.get_analytics_snapshot(app, now_ms=now_ms)

        self.assertEqual(snapshot["revenueTotal"], 250)
        self.assertEqual(app.store.get_state(), before)

    def test_analytics_empty_db(self):
        from bot.services import analytics_service

        app = self.make_app()
        now_ms = parse_datetime_local_value("2026-04-08T12:00", app.config.app_timezone)

        snapshot = analytics_service.get_analytics_snapshot(app, now_ms=now_ms)

        self.assertEqual(snapshot["stats"]["totalUsers"], 0)
        self.assertEqual(snapshot["revenueDay"], 0)
        self.assertEqual(snapshot["revenueWeek"], 0)
        self.assertEqual(snapshot["revenueMonth"], 0)
        self.assertEqual(snapshot["topUsers"], [])

    def test_active_expired_counts_correct(self):
        from bot.services import analytics_service

        app = self.make_app()
        now_ms = parse_datetime_local_value("2026-04-08T12:00", app.config.app_timezone)
        app.store.ensure_user({"id": 10, "first_name": "Active", "username": "active"})
        app.store.ensure_user({"id": 11, "first_name": "Expired", "username": "expired"})
        app.store.ensure_user({"id": 12, "first_name": "Soon", "username": "soon"})
        app.store.update_user_fields(10, {"subscriptionUntil": now_ms + (10 * 24 * 3600 * 1000)})
        app.store.update_user_fields(11, {"subscriptionUntil": now_ms - 1000})
        app.store.update_user_fields(12, {"subscriptionUntil": now_ms + (2 * 24 * 3600 * 1000)})
        app.store.set_user_pending_join_request(12, {"chatId": -100123, "createdAt": now_ms})

        snapshot = analytics_service.get_analytics_snapshot(app, now_ms=now_ms)

        self.assertEqual(snapshot["stats"]["totalUsers"], 3)
        self.assertEqual(snapshot["stats"]["activeSubscriptions"], 2)
        self.assertEqual(snapshot["stats"]["expiredSubscriptions"], 1)
        self.assertEqual(snapshot["stats"]["expiringSoon"], 1)
        self.assertEqual(snapshot["stats"]["pendingJoinRequests"], 1)

    def test_revenue_day_week_month_correct(self):
        from bot.services import analytics_service

        app = self.make_app()
        now_ms = parse_datetime_local_value("2026-04-08T12:00", app.config.app_timezone)
        self.ensure_payment(app, 21, "charge_day", 100, parse_datetime_local_value("2026-04-08T09:00", app.config.app_timezone))
        self.ensure_payment(app, 22, "charge_week", 200, parse_datetime_local_value("2026-04-07T10:00", app.config.app_timezone))
        self.ensure_payment(app, 23, "charge_month", 300, parse_datetime_local_value("2026-04-02T10:00", app.config.app_timezone))
        self.ensure_payment(app, 24, "charge_total", 400, parse_datetime_local_value("2026-03-31T23:30", app.config.app_timezone))

        snapshot = analytics_service.get_analytics_snapshot(app, now_ms=now_ms)

        self.assertEqual(snapshot["revenueDay"], 100)
        self.assertEqual(snapshot["revenueWeek"], 300)
        self.assertEqual(snapshot["revenueMonth"], 600)
        self.assertEqual(snapshot["revenueTotal"], 1000)
        self.assertEqual(snapshot["payersDay"], 1)
        self.assertEqual(snapshot["payersWeek"], 2)
        self.assertEqual(snapshot["payersMonth"], 3)

    def test_top_users_sorted_by_total_spent(self):
        from bot.services import analytics_service

        app = self.make_app()
        now_ms = parse_datetime_local_value("2026-04-08T12:00", app.config.app_timezone)
        self.ensure_payment(app, 31, "charge_top_1a", 300, now_ms - 3000)
        self.ensure_payment(app, 31, "charge_top_1b", 100, now_ms - 2000)
        self.ensure_payment(app, 32, "charge_top_2", 350, now_ms - 1000)
        self.ensure_payment(app, 33, "charge_top_3", 50, now_ms - 500)

        snapshot = analytics_service.get_analytics_snapshot(app, now_ms=now_ms)
        top_ids = [item["userId"] for item in snapshot["topUsers"]]

        self.assertEqual(top_ids[:3], [31, 32, 33])
        self.assertEqual(snapshot["topUsers"][0]["totalSpentStars"], 400)
        self.assertEqual(snapshot["topUsers"][0]["totalPaymentsCount"], 2)

    def test_timezone_boundary_cases(self):
        from bot.services import analytics_service

        app = self.make_app()
        now_ms = parse_datetime_local_value("2026-04-01T00:30", app.config.app_timezone)
        self.ensure_payment(app, 41, "charge_before_midnight", 100, parse_datetime_local_value("2026-03-31T23:30", app.config.app_timezone))
        self.ensure_payment(app, 42, "charge_after_midnight", 200, parse_datetime_local_value("2026-04-01T00:05", app.config.app_timezone))

        snapshot = analytics_service.get_analytics_snapshot(app, now_ms=now_ms)

        self.assertEqual(snapshot["revenueDay"], 200)
        self.assertEqual(snapshot["revenueMonth"], 200)
        self.assertEqual(snapshot["revenueTotal"], 300)


if __name__ == "__main__":
    unittest.main()

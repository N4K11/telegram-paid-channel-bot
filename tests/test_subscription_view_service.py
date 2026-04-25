import ast
import unittest
from pathlib import Path

from bot.services import subscription_view_service


class SubscriptionViewServiceTests(unittest.TestCase):
    def test_subscription_view_service_imports_without_bot_app_cycle(self):
        relative_path = "bot/services/subscription_view_service.py"
        tree = ast.parse(Path(relative_path).read_text(encoding="utf-8-sig"), filename=relative_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "bot.app")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "bot.app")

    def test_format_days_left_pluralization(self):
        now_ms = 1_700_000_000_000
        self.assertEqual(
            subscription_view_service.format_days_left(now_ms + subscription_view_service.DAY_MS, now_ms=now_ms),
            "1 день",
        )
        self.assertEqual(
            subscription_view_service.format_days_left(now_ms + subscription_view_service.DAY_MS * 3, now_ms=now_ms),
            "3 дня",
        )
        self.assertEqual(
            subscription_view_service.format_days_left(now_ms + subscription_view_service.DAY_MS * 5, now_ms=now_ms),
            "5 дней",
        )

    def test_build_main_menu_status_lines_for_active_user(self):
        now_ms = 1_700_000_000_000
        lines = subscription_view_service.build_main_menu_status_lines(
            {
                "user": {"subscriptionUntil": now_ms + subscription_view_service.DAY_MS * 3},
                "system": {"appTimezone": "UTC"},
                "is_active": True,
                "effective_invite_link": "https://t.me/+active_link",
            },
            now_ms=now_ms,
        )

        self.assertIn("Статус: <b>активна</b>", lines[0])
        self.assertIn("Осталось: <b>3 дня</b>.", lines[1])
        self.assertEqual(lines[2], "Если вы ещё не в канале, нажмите «Открыть канал» ниже и отправьте заявку.")

    def test_build_main_menu_status_lines_for_pending_inactive_user(self):
        lines = subscription_view_service.build_main_menu_status_lines(
            {
                "user": {"pendingJoinRequest": {"chatId": -100123}},
                "system": {"appTimezone": "UTC"},
                "is_active": False,
                "effective_invite_link": "",
            }
        )

        self.assertEqual(lines[0], "Статус: <b>не активна</b>.")
        self.assertEqual(lines[1], "Заявка в канал уже отправлена. Оплатите доступ, и бот одобрит её автоматически.")

    def test_build_help_text_includes_post_payment_guidance(self):
        text = subscription_view_service.build_help_text("support_manager")

        self.assertIn("Что делать после оплаты?", text)
        self.assertIn("Если заявка уже отправлена?", text)
        self.assertIn("@support_manager", text)

    def test_build_balance_purchase_notice_contains_subscription_date(self):
        notice = subscription_view_service.build_balance_purchase_notice(
            {"subscriptionUntil": 1_700_000_000_000 + subscription_view_service.DAY_MS},
            "UTC",
        )

        self.assertIn("Подписка успешно оплачена с баланса", notice)
        self.assertIn("активна до <b>", notice)


if __name__ == "__main__":
    unittest.main()

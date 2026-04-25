import ast
import unittest
from pathlib import Path

from bot import ui as ui_module
from bot.ui import UIProvider


class UIContractsTests(unittest.TestCase):
    @staticmethod
    def _keyboard_signature(markup):
        signature = []
        for row in markup.get("inline_keyboard", []):
            row_signature = []
            for button in row:
                row_signature.append(
                    (
                        button.get("text"),
                        button.get("callback_data"),
                        button.get("url"),
                    )
                )
            signature.append(row_signature)
        return signature

    @staticmethod
    def _all_callback_data(markup):
        values = []
        for row in markup.get("inline_keyboard", []):
            for button in row:
                if "callback_data" in button:
                    values.append(button["callback_data"])
        return values

    def test_bot_ui_public_api_preserved(self):
        expected = {
            "get_main_menu",
            "get_user_help",
            "get_admin_main",
            "get_admin_settings",
            "get_admin_users",
            "get_admin_user_details",
            "get_admin_payment_diagnostics",
            "get_admin_payment_anomalies",
            "get_admin_templates_menu",
            "get_admin_template_editor",
            "get_admin_broadcast_menu",
        }
        for name in expected:
            self.assertTrue(hasattr(ui_module, name))
            self.assertTrue(callable(getattr(ui_module, name)))
            self.assertTrue(hasattr(UIProvider, name))
            self.assertTrue(callable(getattr(UIProvider, name)))

    def test_ui_modules_import_without_bot_app_cycle(self):
        for relative_path in [
            "bot/ui.py",
            "bot/ui_common.py",
            "bot/ui_user.py",
            "bot/ui_admin.py",
        ]:
            tree = ast.parse(Path(relative_path).read_text(encoding="utf-8-sig"), filename=relative_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotEqual(alias.name, "bot.app")
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, "bot.app")

    def test_user_main_menu_keyboard_contract(self):
        _, markup = UIProvider.get_main_menu(
            {
                "settings": {
                    "subscriptionName": "Test Subscription",
                    "welcomeText": "Welcome",
                    "subscriptionPriceStars": 250,
                    "subscriptionDurationDays": 30,
                    "supportUsername": "support_manager",
                },
                "user": {"balanceStars": 300},
                "is_active": False,
                "effective_invite_link": "",
                "system": {"appTimezone": "Europe/Saratov"},
                "notice": None,
                "is_admin": True,
            }
        )

        self.assertEqual(
            self._keyboard_signature(markup),
            [
                [("💳 Купить доступ", "buy", None)],
                [("📥 Получить ссылку", "join", None), ("❓ Помощь", "user:help", None)],
                [("✨ Оплатить с баланса", "buy_balance", None)],
                [("🆘 Поддержка", None, "https://t.me/support_manager"), ("⚙️ Админка", "admin:menu", None)],
            ],
        )

    def test_user_main_menu_text_contract_for_inactive_user(self):
        text, _ = UIProvider.get_main_menu(
            {
                "settings": {
                    "subscriptionName": "Test Subscription",
                    "welcomeText": "Welcome",
                    "subscriptionPriceStars": 250,
                    "subscriptionDurationDays": 30,
                    "supportUsername": "support_manager",
                },
                "user": {"balanceStars": 0},
                "is_active": False,
                "effective_invite_link": "",
                "system": {"appTimezone": "Europe/Saratov"},
                "notice": None,
                "is_admin": False,
            }
        )

        self.assertIn("Статус: <b>не активна</b>.", text)
        self.assertIn("После оплаты используйте кнопку «Получить ссылку»", text)

    def test_user_main_menu_text_contract_for_active_user(self):
        text, _ = UIProvider.get_main_menu(
            {
                "settings": {
                    "subscriptionName": "Test Subscription",
                    "welcomeText": "Welcome",
                    "subscriptionPriceStars": 250,
                    "subscriptionDurationDays": 30,
                    "supportUsername": "support_manager",
                },
                "user": {"balanceStars": 0, "subscriptionUntil": 4102444800000},
                "is_active": True,
                "effective_invite_link": "https://t.me/+active_link",
                "system": {"appTimezone": "Europe/Saratov"},
                "notice": None,
                "is_admin": False,
            }
        )

        self.assertIn("Статус: <b>активна</b>", text)
        self.assertIn("Осталось: <b>", text)
        self.assertIn("Если вы ещё не в канале, нажмите «Открыть канал» ниже", text)

    def test_user_help_or_join_keyboard_contract(self):
        _, help_markup = UIProvider.get_user_help("support_manager")
        self.assertEqual(
            self._keyboard_signature(help_markup),
            [
                [("🔙 Назад", "panel:main", None)],
            ],
        )

        _, active_markup = UIProvider.get_main_menu(
            {
                "settings": {
                    "subscriptionName": "Test Subscription",
                    "welcomeText": "Welcome",
                    "subscriptionPriceStars": 250,
                    "subscriptionDurationDays": 30,
                    "supportUsername": "support_manager",
                },
                "user": {"balanceStars": 0, "subscriptionUntil": 4102444800000},
                "is_active": True,
                "effective_invite_link": "https://t.me/+active_link",
                "system": {"appTimezone": "Europe/Saratov"},
                "notice": None,
                "is_admin": False,
            }
        )
        self.assertEqual(
            self._keyboard_signature(active_markup)[:2],
            [
                [("🚀 Продлить доступ", "buy", None)],
                [("🔗 Открыть канал", None, "https://t.me/+active_link"), ("❓ Помощь", "user:help", None)],
            ],
        )

    def test_user_help_text_contract(self):
        text, _ = UIProvider.get_user_help("support_manager")
        self.assertIn("Что делать после оплаты?", text)
        self.assertIn("Если заявка уже отправлена?", text)
        self.assertIn("@support_manager", text)

    def test_admin_main_menu_keyboard_contract(self):
        _, markup = UIProvider.get_admin_main(
            {
                "totalUsers": 1,
                "activeSubscriptions": 1,
                "channelMembers": 1,
                "pendingJoinRequests": 0,
                "revenueStars": 10,
                "revenueMonth": 10,
            },
            {"channelId": "@privatechannel"},
            "",
        )
        self.assertEqual(
            self._keyboard_signature(markup),
            [
                [("👥 Пользователи", "admin:users:0", None), ("📊 Статистика", "admin:stats", None)],
                [("⚙️ Настройки", "admin:settings", None), ("📢 Рассылка", "admin:broadcast:menu", None)],
                [("🧾 Аномалии оплат", "admin:payment_anomalies", None), ("🔄 Обновить invite", "admin:refresh_invite", None)],
                [("🏠 Главное меню", "panel:main", None)],
            ],
        )

    def test_admin_settings_keyboard_contract(self):
        _, markup = UIProvider.get_admin_settings(
            {
                "subscriptionPriceStars": 250,
                "subscriptionDurationDays": 30,
                "warningDays": 3,
                "supportUsername": "support_manager",
            },
            {"autoCreateInviteLink": True},
        )
        self.assertEqual(
            self._keyboard_signature(markup),
            [
                [("💰 Цена", "admin:input:price", None), ("⏳ Срок", "admin:input:days", None), ("🔔 Варн", "admin:input:warning", None)],
                [("🔄 Recurring", "admin:toggle:recurring", None), ("🔗 Авто-invite", "admin:toggle:autoinvite", None)],
                [("📡 Канал", "admin:input:channel", None), ("🆘 Поддержка", "admin:input:support", None)],
                [("📝 Редактировать тексты", "admin:templates:menu", None)],
                [("🔙 Назад", "admin:menu", None)],
            ],
        )

    def test_admin_payment_anomalies_button_contract(self):
        _, markup = UIProvider.get_admin_main(
            {
                "totalUsers": 1,
                "activeSubscriptions": 1,
                "channelMembers": 1,
                "pendingJoinRequests": 0,
                "revenueStars": 10,
                "revenueMonth": 10,
            },
            {"channelId": "@privatechannel"},
            "",
        )
        self.assertEqual(self._keyboard_signature(markup)[2][0], ("🧾 Аномалии оплат", "admin:payment_anomalies", None))

    def test_no_duplicate_callback_data_in_same_keyboard(self):
        keyboards = [
            UIProvider.get_main_menu(
                {
                    "settings": {
                        "subscriptionName": "Test Subscription",
                        "welcomeText": "Welcome",
                        "subscriptionPriceStars": 250,
                        "subscriptionDurationDays": 30,
                        "supportUsername": "support_manager",
                    },
                    "user": {"balanceStars": 300},
                    "is_active": False,
                    "effective_invite_link": "",
                    "system": {"appTimezone": "Europe/Saratov"},
                    "notice": None,
                    "is_admin": True,
                }
            )[1],
            UIProvider.get_user_help("support_manager")[1],
            UIProvider.get_admin_main(
                {
                    "totalUsers": 1,
                    "activeSubscriptions": 1,
                    "channelMembers": 1,
                    "pendingJoinRequests": 0,
                    "revenueStars": 10,
                    "revenueMonth": 10,
                },
                {"channelId": "@privatechannel"},
                "",
            )[1],
            UIProvider.get_admin_settings(
                {
                    "subscriptionPriceStars": 250,
                    "subscriptionDurationDays": 30,
                    "warningDays": 3,
                    "supportUsername": "support_manager",
                },
                {"autoCreateInviteLink": True},
            )[1],
        ]

        for markup in keyboards:
            callbacks = self._all_callback_data(markup)
            self.assertEqual(len(callbacks), len(set(callbacks)))

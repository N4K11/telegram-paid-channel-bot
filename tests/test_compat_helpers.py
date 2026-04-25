import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import bot.compat_helpers as compat_helpers
from bot.app import SubscriptionBotApp


PUBLIC_COMPAT_FUNCTIONS = {
    "get_admin_view_model",
    "get_user_editor_view_model",
    "replace_state_from_json",
    "replace_settings_from_json",
    "replace_templates_from_json",
    "save_user_structured",
    "replace_user_json",
    "delete_user",
    "format_stats_text",
    "get_template_context",
    "render_message_template",
    "configure_channel",
    "get_dashboard_stats_extended",
}


class CompatHelpersTests(unittest.TestCase):
    def test_compat_helpers_public_api_exists(self):
        for name in PUBLIC_COMPAT_FUNCTIONS:
            self.assertTrue(hasattr(compat_helpers, name), msg=f"Missing compat helper: {name}")
            self.assertTrue(callable(getattr(compat_helpers, name)), msg=f"Compat helper is not callable: {name}")

    def test_bot_app_still_reexports_compat_helpers(self):
        for name in PUBLIC_COMPAT_FUNCTIONS:
            self.assertTrue(hasattr(SubscriptionBotApp, name), msg=f"Missing bot.app wrapper: {name}")
            self.assertTrue(callable(getattr(SubscriptionBotApp, name)), msg=f"bot.app wrapper is not callable: {name}")

    def test_compat_helpers_reject_invalid_json(self):
        invalid_json = "{"

        test_cases = [
            (compat_helpers.replace_state_from_json, (invalid_json,), "replace_state"),
            (compat_helpers.replace_settings_from_json, (invalid_json,), "replace_settings"),
            (compat_helpers.replace_templates_from_json, (invalid_json,), "update_settings"),
            (compat_helpers.replace_user_json, (123, invalid_json), "replace_user"),
        ]

        for func, args, attr_name in test_cases:
            with self.subTest(func=func.__name__):
                fake_store = MagicMock()
                fake_app = SimpleNamespace(store=fake_store)
                with self.assertRaises(json.JSONDecodeError):
                    func(fake_app, *args)
                getattr(fake_store, attr_name).assert_not_called()

    def test_template_rendering_preserves_unknown_placeholders(self):
        fake_store = SimpleNamespace(
            get_settings=lambda: {
                "messageTemplates": {
                    "sample": "Hello {{unknown}} {{firstName}}",
                },
                "supportUsername": "support_manager",
                "subscriptionName": "Subscription",
                "subscriptionPriceStars": 250,
            },
            get_user=lambda user_id: {
                "id": user_id,
                "username": "tester",
                "firstName": "Ivan",
                "lastName": "",
                "subscriptionUntil": None,
            },
            get_effective_invite_link=lambda invite_link="": invite_link,
        )
        fake_app = SimpleNamespace(
            store=fake_store,
            config=SimpleNamespace(channel_invite_link=""),
            get_effective_system_settings=lambda: {"appTimezone": "Europe/Saratov"},
        )

        rendered = compat_helpers.render_message_template(fake_app, "sample", 1)

        self.assertEqual(rendered, "Hello {{unknown}} Ivan")

    def test_configure_channel_does_not_require_real_telegram(self):
        fake_store = MagicMock()
        fake_app = SimpleNamespace(
            store=fake_store,
            refresh_invite_link=MagicMock(),
        )

        compat_helpers.configure_channel(fake_app, "https://t.me/my_private_channel?start=1")

        fake_store.update_settings.assert_called_once_with({"channelId": "@my_private_channel"})
        fake_app.refresh_invite_link.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
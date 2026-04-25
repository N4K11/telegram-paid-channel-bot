import ast
import importlib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class DispatcherTests(unittest.TestCase):
    def test_dispatcher_module_imports_without_bot_app_cycle(self):
        module = importlib.import_module("bot.dispatcher")
        self.assertTrue(hasattr(module, "dispatch_update"))
        self.assertTrue(hasattr(module, "dispatch_message"))
        self.assertTrue(hasattr(module, "dispatch_callback_query"))

        tree = ast.parse(Path("bot/dispatcher.py").read_text(encoding="utf-8-sig"), filename="bot/dispatcher.py")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "bot.app")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "bot.app")

    def test_dispatch_update_routes_message(self):
        from bot import dispatcher

        app = SimpleNamespace(
            handle_message=MagicMock(),
            handle_callback_query=MagicMock(),
            handle_pre_checkout_query=MagicMock(),
            handle_chat_join_request=MagicMock(),
        )

        dispatcher.dispatch_update(app, {"message": {"message_id": 1}})

        app.handle_message.assert_called_once_with({"message_id": 1})
        app.handle_callback_query.assert_not_called()
        app.handle_pre_checkout_query.assert_not_called()
        app.handle_chat_join_request.assert_not_called()

    def test_dispatch_update_routes_callback(self):
        from bot import dispatcher

        app = SimpleNamespace(
            handle_message=MagicMock(),
            handle_callback_query=MagicMock(),
            handle_pre_checkout_query=MagicMock(),
            handle_chat_join_request=MagicMock(),
        )

        dispatcher.dispatch_update(app, {"callback_query": {"id": "cb1"}})

        app.handle_callback_query.assert_called_once_with({"id": "cb1"})
        app.handle_message.assert_not_called()
        app.handle_pre_checkout_query.assert_not_called()
        app.handle_chat_join_request.assert_not_called()

    def test_dispatch_update_routes_pre_checkout(self):
        from bot import dispatcher

        app = SimpleNamespace(
            handle_message=MagicMock(),
            handle_callback_query=MagicMock(),
            handle_pre_checkout_query=MagicMock(),
            handle_chat_join_request=MagicMock(),
        )

        dispatcher.dispatch_update(app, {"pre_checkout_query": {"id": "pq1"}})

        app.handle_pre_checkout_query.assert_called_once_with({"id": "pq1"})
        app.handle_message.assert_not_called()
        app.handle_callback_query.assert_not_called()
        app.handle_chat_join_request.assert_not_called()

    def test_dispatch_update_routes_chat_join_request(self):
        from bot import dispatcher

        app = SimpleNamespace(
            handle_message=MagicMock(),
            handle_callback_query=MagicMock(),
            handle_pre_checkout_query=MagicMock(),
            handle_chat_join_request=MagicMock(),
        )

        dispatcher.dispatch_update(app, {"chat_join_request": {"from": {"id": 5}}})

        app.handle_chat_join_request.assert_called_once_with({"from": {"id": 5}})
        app.handle_message.assert_not_called()
        app.handle_callback_query.assert_not_called()
        app.handle_pre_checkout_query.assert_not_called()

    def test_dispatch_message_successful_payment_priority(self):
        from bot import dispatcher

        app = SimpleNamespace(
            _ensure_user_context=MagicMock(return_value=10),
            admin_handler=SimpleNamespace(handle_text=MagicMock(return_value=False)),
            user_handler=SimpleNamespace(handle_command=MagicMock()),
            ADMIN_COMMANDS={"/admin"},
        )
        message = {
            "from": {"id": 10},
            "successful_payment": {"telegram_payment_charge_id": "charge_10"},
            "text": "/start",
        }

        with patch.object(dispatcher, "dispatch_successful_payment", return_value={"status": "processed"}) as payment_mock:
            dispatcher.dispatch_message(app, message)

        payment_mock.assert_called_once_with(app, message)
        app.admin_handler.handle_text.assert_not_called()
        app.user_handler.handle_command.assert_not_called()

    def test_admin_command_routing_preserved(self):
        from bot import dispatcher

        telegram = SimpleNamespace(send_message=MagicMock())
        app = SimpleNamespace(
            _handle_admin_login=MagicMock(),
            _handle_admin_logout=MagicMock(),
            is_authorized_admin=MagicMock(return_value=True),
            get_telegram=MagicMock(return_value=telegram),
            admin_handler=SimpleNamespace(
                _render_payment_anomalies=MagicMock(),
                _render_payment_diagnostics=MagicMock(),
                _render_user_details=MagicMock(),
            ),
            manual_recover_payment_access=MagicMock(),
            _dispatch_admin_command=MagicMock(),
        )
        message = {"from": {"id": 900}}

        dispatcher.dispatch_admin_command(app, message, "/admin_payment_anomalies", "50")

        app.admin_handler._render_payment_anomalies.assert_called_once_with(900, 50)
        telegram.send_message.assert_not_called()
        app._dispatch_admin_command.assert_not_called()

    def test_user_start_routing_preserved(self):
        from bot import dispatcher

        app = SimpleNamespace(
            _ensure_user_context=MagicMock(return_value=11),
            admin_handler=SimpleNamespace(handle_text=MagicMock(return_value=False)),
            user_handler=SimpleNamespace(handle_command=MagicMock()),
            ADMIN_COMMANDS={"/admin"},
        )
        message = {"from": {"id": 11}, "text": "/start"}

        dispatcher.dispatch_message(app, message)

        app.user_handler.handle_command.assert_called_once_with(message, "/start", None)

    def test_callback_routing_preserves_known_callbacks(self):
        from bot import dispatcher

        app = SimpleNamespace(
            _ensure_user_context=MagicMock(return_value=12),
            admin_handler=SimpleNamespace(handle_callback=MagicMock()),
            user_handler=SimpleNamespace(handle_callback=MagicMock()),
        )

        dispatcher.dispatch_callback_query(app, {"id": "cb1", "from": {"id": 12}, "data": "admin:menu"})
        dispatcher.dispatch_callback_query(app, {"id": "cb2", "from": {"id": 12}, "data": "buy"})

        app.admin_handler.handle_callback.assert_called_once_with({"id": "cb1", "from": {"id": 12}, "data": "admin:menu"})
        app.user_handler.handle_callback.assert_called_once_with({"id": "cb2", "from": {"id": 12}, "data": "buy"})

    def test_unknown_callback_behavior_preserved(self):
        from bot import dispatcher

        app = SimpleNamespace(
            _ensure_user_context=MagicMock(return_value=13),
            admin_handler=SimpleNamespace(handle_callback=MagicMock()),
            user_handler=SimpleNamespace(handle_callback=MagicMock()),
        )
        callback_query = {"id": "cb3", "from": {"id": 13}, "data": "unknown:noop"}

        dispatcher.dispatch_callback_query(app, callback_query)

        app.admin_handler.handle_callback.assert_not_called()
        app.user_handler.handle_callback.assert_called_once_with(callback_query)

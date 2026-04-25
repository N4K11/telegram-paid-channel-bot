import ast
import io
import logging
import unittest
from pathlib import Path

from bot import logging_config


class LoggingConfigTests(unittest.TestCase):
    def test_logging_config_imports_without_bot_app_cycle(self):
        tree = ast.parse(
            Path("bot/logging_config.py").read_text(encoding="utf-8-sig"),
            filename="bot/logging_config.py",
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "bot.app")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "bot.app")

    def test_logger_created_and_idempotent(self):
        logger = logging_config.configure_logging()
        again = logging_config.configure_logging()

        self.assertIs(logger, again)
        self.assertGreaterEqual(len(logger.handlers), 1)

    def test_sensitive_values_redacted_in_formatted_logs(self):
        logger = logging.getLogger("private_channel_bot.test.logging")
        logger.handlers.clear()
        logger.propagate = False
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging_config.RedactingFormatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logging_config.log_event(
            logger,
            "telegram_api_error",
            error="Forbidden: bad token 123456789:ABCDEF_token_hidden_example",
            invite="https://t.me/+supersecretinvite",
        )

        payload = stream.getvalue()
        self.assertIn("event=telegram_api_error", payload)
        self.assertIn("<redacted-token>", payload)
        self.assertIn("<redacted-invite-link>", payload)
        self.assertNotIn("123456789:ABCDEF_token_hidden_example", payload)
        self.assertNotIn("https://t.me/+supersecretinvite", payload)


if __name__ == "__main__":
    unittest.main()

import json
import logging
import re
import sys


TOKEN_PATTERN = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b")
PRIVATE_INVITE_PATTERN = re.compile(r"https://t\.me/\+[A-Za-z0-9_-]+")


def sanitize_text(value):
    text = str(value or "").strip()
    if not text:
        return ""
    text = TOKEN_PATTERN.sub("<redacted-token>", text)
    text = PRIVATE_INVITE_PATTERN.sub("<redacted-invite-link>", text)
    return text


def _format_field_value(value):
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list, tuple)):
        return sanitize_text(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return sanitize_text(value)


def format_event(event, **fields):
    parts = [f"event={sanitize_text(event)}"]
    for key in sorted(fields):
        parts.append(f"{key}={json.dumps(_format_field_value(fields[key]), ensure_ascii=False)}")
    return " ".join(parts)


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return sanitize_text(super().format(record))


def configure_logging(level=logging.INFO):
    logger = logging.getLogger("private_channel_bot")
    if getattr(logger, "_codex_configured", False):
        return logger

    logger.setLevel(level)
    logger.propagate = False

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )

    logger.handlers.clear()
    logger.addHandler(handler)
    logger._codex_configured = True
    return logger


def get_logger(name="runtime"):
    base_logger = configure_logging()
    if not name or name == "private_channel_bot":
        return base_logger
    full_name = name if name.startswith("private_channel_bot") else f"private_channel_bot.{name}"
    logger = logging.getLogger(full_name)
    logger.setLevel(base_logger.level)
    return logger


def log_event(logger, event, level=logging.INFO, **fields):
    logger.log(level, format_event(event, **fields))


def log_app_event(app, event, level=logging.INFO, **fields):
    logger = getattr(app, "log_event", None)
    if callable(logger):
        logger(event, level=level, **fields)


def classify_error_event(context, error):
    combined = f"{context} {error}".lower()
    if "channel diagnostics" in combined:
        return "channel_diagnostics_failed"
    if "health check" in combined or "healthcheck" in combined:
        return "health_check_failed"
    if "store file" in combined or "save failed" in combined:
        return "store_save_error"
    if "telegram api" in combined:
        return "telegram_api_error"
    return "runtime_error"

import os
import secrets
from dataclasses import dataclass


@dataclass
class Config:
    bot_token: str
    channel_id: str
    admin_username: str
    admin_password: str
    admin_telegram_id: str
    subscription_price_stars: int
    subscription_duration_days: int
    warning_days: int
    recurring_payments_enabled: bool
    subscription_name: str
    subscription_description: str
    support_username: str
    welcome_text: str
    app_timezone: str
    base_url: str
    port: int
    auto_create_invite_link: bool
    channel_invite_link: str
    poll_timeout_seconds: int
    service_check_interval_ms: int
    data_file_path: str
    session_secret: str
    telegram_api_base_url: str


def load_dotenv(dotenv_path=".env"):
    if not os.path.exists(dotenv_path):
        return

    with open(dotenv_path, "r", encoding="utf-8") as file:
        for raw_line in file.readlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]

            if key not in os.environ:
                os.environ[key] = value


def parse_bool(value, fallback):
    if value is None or value == "":
        return fallback
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_int(value, fallback):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def get_config():
    port = parse_int(os.getenv("PORT"), 3000)
    data_file_path = os.getenv("DATA_FILE_PATH") or os.path.join(os.getcwd(), "data", "db.json")
    return Config(
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        channel_id=os.getenv("TELEGRAM_CHANNEL_ID", ""),
        admin_username=os.getenv("ADMIN_USERNAME", "admin"),
        admin_password=os.getenv("ADMIN_PASSWORD", ""),
        admin_telegram_id=os.getenv("ADMIN_TELEGRAM_ID", "").strip(),
        subscription_price_stars=max(1, parse_int(os.getenv("SUBSCRIPTION_PRICE_STARS"), 250)),
        subscription_duration_days=max(1, parse_int(os.getenv("SUBSCRIPTION_DURATION_DAYS"), 30)),
        warning_days=max(1, parse_int(os.getenv("WARNING_DAYS"), 3)),
        recurring_payments_enabled=parse_bool(os.getenv("RECURRING_PAYMENTS_ENABLED"), False),
        subscription_name=os.getenv("SUBSCRIPTION_NAME", "Доступ в приватный канал"),
        subscription_description=os.getenv("SUBSCRIPTION_DESCRIPTION", "Оплата доступа к приватному Telegram-каналу"),
        support_username=os.getenv("SUPPORT_USERNAME", "").strip().lstrip("@"),
        welcome_text=os.getenv("WELCOME_TEXT", "Оформите подписку, и бот выдаст доступ в приватный канал."),
        app_timezone=os.getenv("APP_TIMEZONE", "Europe/Saratov"),
        base_url=os.getenv("BASE_URL", f"http://localhost:{port}"),
        port=port,
        auto_create_invite_link=parse_bool(os.getenv("AUTO_CREATE_INVITE_LINK"), True),
        channel_invite_link=os.getenv("CHANNEL_INVITE_LINK", ""),
        poll_timeout_seconds=parse_int(os.getenv("POLL_TIMEOUT_SECONDS"), 25),
        service_check_interval_ms=parse_int(os.getenv("SERVICE_CHECK_INTERVAL_MS"), 60000),
        data_file_path=data_file_path,
        session_secret=os.getenv("SESSION_SECRET", secrets.token_hex(32)),
        telegram_api_base_url=os.getenv("TELEGRAM_API_BASE_URL", "https://api.telegram.org"),
    )


def validate_config(config):
    missing = []
    if not config.bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not config.channel_id:
        missing.append("TELEGRAM_CHANNEL_ID")
    if not config.admin_password and not config.admin_telegram_id:
        missing.append("ADMIN_PASSWORD or ADMIN_TELEGRAM_ID")

    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

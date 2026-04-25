import hashlib
import hmac
import html
import json
from datetime import datetime, timezone
from urllib.parse import parse_qsl, unquote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def normalize_search(value):
    return str(value or "").strip().lower()


def to_nullable_text(value):
    text = str(value or "").strip()
    return text if text else None


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def add_days(timestamp_ms, days):
    return int(timestamp_ms + days * 24 * 60 * 60 * 1000)


def escape_html(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def resolve_timezone(time_zone):
    try:
        return ZoneInfo(time_zone or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def format_datetime(timestamp_ms, time_zone):
    if not timestamp_ms:
        return "—"

    zone = resolve_timezone(time_zone)
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).astimezone(zone)
    return dt.strftime("%d.%m.%Y %H:%M")


def format_datetime_local_value(timestamp_ms, time_zone):
    if not timestamp_ms:
        return ""

    zone = resolve_timezone(time_zone)
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).astimezone(zone)
    return dt.strftime("%Y-%m-%dT%H:%M")


def parse_datetime_local_value(value, time_zone):
    text = str(value or "").strip()
    if not text:
        return None

    zone = resolve_timezone(time_zone)
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=zone)
        else:
            dt = dt.astimezone(zone)
        return int(dt.astimezone(timezone.utc).timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def format_relative_duration(target_ms, now_ms=None):
    if not target_ms:
        return "—"

    if now_ms is None:
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)

    diff = int(target_ms - now_ms)
    absolute = abs(diff)
    day_ms = 24 * 60 * 60 * 1000
    hour_ms = 60 * 60 * 1000

    if absolute >= day_ms:
        days = max(1, round(absolute / day_ms))
        return f"через {days} дн." if diff >= 0 else f"{days} дн. назад"

    hours = max(1, round(absolute / hour_ms))
    return f"через {hours} ч." if diff >= 0 else f"{hours} ч. назад"


def format_user_name(user):
    if not user:
        return "Пользователь"

    parts = [user.get("firstName"), user.get("lastName")]
    parts = [part for part in parts if part]
    if parts:
        return " ".join(parts)

    username = user.get("username")
    if username:
        return f"@{username}"

    return f"ID {user.get('id', '-')}"


def create_signature(secret, value):
    secret_bytes = str(secret or "").encode("utf-8")
    value_bytes = str(value or "").encode("utf-8")
    return hmac.new(secret_bytes, value_bytes, hashlib.sha256).hexdigest()


def parse_cookies(header_value):
    cookies = {}
    if not header_value:
        return cookies

    for item in header_value.split(";"):
        chunk = item.strip()
        if not chunk or "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        cookies[key.strip()] = unquote(value.strip())

    return cookies


def parse_form_encoded(body_bytes):
    text = body_bytes.decode("utf-8")
    return dict(parse_qsl(text, keep_blank_values=True))


def parse_integer(value, fallback=0):
    try:
        return int(str(value).strip())
    except (AttributeError, TypeError, ValueError):
        return fallback


def parse_boolean_from_form(value):
    return str(value or "").strip().lower() in {"on", "true", "1", "yes"}


def to_json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

from bot import logging_config
import os
import re
import tempfile

from utils_py import format_datetime


TOKEN_PATTERN = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b")
PRIVATE_INVITE_PATTERN = re.compile(r"https://t\.me/\+[A-Za-z0-9_-]+")


def _sanitize_error_text(message):
    text = str(message or "").strip()
    if not text:
        return ""
    text = TOKEN_PATTERN.sub("<redacted-token>", text)
    text = PRIVATE_INVITE_PATTERN.sub("<redacted-invite-link>", text)
    return text


def _format_bool(value):
    return "yes" if value else "no"


def _format_uptime(uptime_ms):
    total_seconds = max(0, int((uptime_ms or 0) / 1000))
    days, rem = divmod(total_seconds, 24 * 3600)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _check_store_writable(file_path):
    directory = os.path.dirname(file_path) or "."
    temp_path = None
    try:
        os.makedirs(directory, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=".healthcheck-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write("ok")
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = handle.name
        os.remove(temp_path)
        return {"ok": True, "error": ""}
    except Exception as error:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return {"ok": False, "error": _sanitize_error_text(error)}


def _resolve_bot_info(app):
    bot_info = app.store.get_meta().get("botInfo")
    if bot_info:
        return {
            "id": bot_info.get("id"),
            "username": bot_info.get("username") or "",
        }, ""

    try:
        bot_info = app.get_telegram().get_me()
        return {
            "id": bot_info.get("id"),
            "username": bot_info.get("username") or "",
        }, ""
    except Exception as error:
        return None, _sanitize_error_text(error)


def _serialize_runtime_error(app):
    runtime_error = getattr(app, "last_runtime_error", None) or {}
    if not runtime_error:
        return {"context": "", "error": "", "loggedAt": None}
    return {
        "context": str(runtime_error.get("context") or "").strip(),
        "error": _sanitize_error_text(runtime_error.get("error")),
        "loggedAt": runtime_error.get("loggedAt"),
    }


def get_health_status(app):
    now_ms = int(app._now_ms())
    system = app.get_effective_system_settings()
    meta = app.store.get_meta()
    stats = app.store.get_dashboard_stats(current_time_ms=now_ms)
    bot_info, bot_info_error = _resolve_bot_info(app)
    writable = _check_store_writable(app.store.file_path)
    backup_dir = os.path.join(os.path.dirname(app.store.file_path) or ".", "backups")
    runtime_error = _serialize_runtime_error(app)

    if bot_info_error:
        logging_config.log_app_event(app, "health_check_failed", check="bot_info", error=bot_info_error)
    if writable["error"]:
        logging_config.log_app_event(app, "health_check_failed", check="store_writable", error=writable["error"])

    return {
        "uptimeMs": max(0, now_ms - int(getattr(app, "started_at_ms", now_ms))),
        "botInfo": bot_info,
        "botInfoError": bot_info_error,
        "channelConfigured": bool(system.get("channelId")),
        "channelId": system.get("channelId") or "",
        "storeWritable": writable["ok"],
        "storeWritableError": writable["error"],
        "lastUpdateId": meta.get("lastUpdateId") or 0,
        "maintenanceLastRunAt": getattr(app, "last_maintenance_run_at", None),
        "activeUsers": stats.get("activeSubscriptions", 0),
        "expiredUsers": stats.get("expiredSubscriptions", 0),
        "pendingJoinRequests": stats.get("pendingJoinRequests", 0),
        "backupDirExists": os.path.isdir(backup_dir),
        "backupDir": backup_dir,
        "lastRuntimeError": runtime_error["error"],
        "lastRuntimeErrorContext": runtime_error["context"],
        "lastRuntimeErrorAt": runtime_error["loggedAt"],
    }


def format_health_status(status, time_zone="UTC"):
    lines = [
        "<b>❤️ Bot healthcheck</b>",
        "",
        f"Uptime: <b>{_format_uptime(status.get('uptimeMs'))}</b>",
    ]

    bot_info = status.get("botInfo")
    if bot_info:
        username = f"@{bot_info['username']}" if bot_info.get("username") else "no username"
        lines.append(f"Bot: <b>{username}</b> (ID <code>{bot_info.get('id')}</code>)")
    else:
        lines.append("Bot: <b>unavailable</b>")

    if status.get("botInfoError"):
        lines.append(f"Bot info error: <code>{status['botInfoError']}</code>")

    lines.extend(
        [
            f"Channel configured: <b>{_format_bool(status.get('channelConfigured'))}</b>",
            f"Store writable: <b>{_format_bool(status.get('storeWritable'))}</b>",
            f"Last update id: <b>{status.get('lastUpdateId', 0)}</b>",
            "Maintenance last run: <b>"
            + format_datetime(status.get("maintenanceLastRunAt"), time_zone)
            + "</b>",
            f"Active users: <b>{status.get('activeUsers', 0)}</b>",
            f"Expired users: <b>{status.get('expiredUsers', 0)}</b>",
            f"Pending join requests: <b>{status.get('pendingJoinRequests', 0)}</b>",
            f"Backup directory exists: <b>{_format_bool(status.get('backupDirExists'))}</b>",
        ]
    )

    if status.get("storeWritableError"):
        lines.append(f"Store writable error: <code>{status['storeWritableError']}</code>")

    if status.get("lastRuntimeError"):
        lines.append(
            "Last runtime/API error: <code>"
            + status["lastRuntimeError"]
            + "</code>"
        )
        if status.get("lastRuntimeErrorContext"):
            lines.append(f"Error context: <code>{status['lastRuntimeErrorContext']}</code>")
        if status.get("lastRuntimeErrorAt"):
            lines.append(
                "Error time: <b>"
                + format_datetime(status.get("lastRuntimeErrorAt"), time_zone)
                + "</b>"
            )

    return "\n".join(lines)


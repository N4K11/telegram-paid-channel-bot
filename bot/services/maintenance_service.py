from bot.services import access_service
from utils_py import format_datetime


DAY_MS = 24 * 3600 * 1000


def warning_window_ms(settings, warning_ms=None):
    if warning_ms is not None:
        return int(warning_ms)
    return int(settings["warningDays"] * DAY_MS)


def should_revoke_access(user, now_ms):
    until = user.get("subscriptionUntil")
    if not until:
        return False
    return until < now_ms and (
        not user.get("lastAccessRevokedAt") or user["lastAccessRevokedAt"] < until
    )


def should_send_warning(user, settings, now_ms, warning_ms=None):
    until = user.get("subscriptionUntil")
    if not until or until <= now_ms:
        return False

    effective_warning_ms = warning_window_ms(settings, warning_ms=warning_ms)
    if (until - now_ms) >= effective_warning_ms:
        return False

    last_warning_at = user.get("lastWarningAt")
    return not last_warning_at or last_warning_at < (until - effective_warning_ms)


def notify_subscription_warning(app, user, settings, now_ms=None, warning_ms=None):
    until = user.get("subscriptionUntil")
    if not until:
        return False

    notice = (
        "\u26a0\ufe0f \u0412\u0430\u0448\u0430 \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0430 \u0441\u043a\u043e\u0440\u043e \u0437\u0430\u043a\u043e\u043d\u0447\u0438\u0442\u0441\u044f: "
        f"{format_datetime(until, app.config.app_timezone)}"
    )
    app.notify_user(user["id"], notice)
    app.store.mark_warning_sent(user["id"])
    return True


def notify_subscription_expired(app, user, settings=None):
    app.notify_user(user["id"], "\u274c \u0412\u0430\u0448\u0430 \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0430 \u0438\u0441\u0442\u0435\u043a\u043b\u0430.")
    return True


def cleanup_stale_pending_requests(app, settings=None, now_ms=None, users=None):
    return access_service.prune_expired_pending_join_requests(app, now_ms=now_ms, users=users)


def process_maintenance_user(app, user, settings, now_ms=None, warning_ms=None):
    if now_ms is None:
        now_ms = app._now_ms()

    until = user.get("subscriptionUntil")
    if not until:
        return

    if should_revoke_access(user, now_ms):
        app.revoke_user_subscription(user["id"], "expired")
        app.store.mark_access_revoked(user["id"])
        notify_subscription_expired(app, user, settings)
    elif should_send_warning(user, settings, now_ms, warning_ms=warning_ms):
        notify_subscription_warning(app, user, settings, now_ms=now_ms, warning_ms=warning_ms)

    cleanup_stale_pending_requests(app, settings=settings, now_ms=now_ms, users=[user])


def run_subscription_maintenance(app, now_ms=None):
    if now_ms is None:
        now_ms = app._now_ms()

    settings = app.store.get_settings()
    warning_ms = warning_window_ms(settings)
    for user in app.store.list_users():
        try:
            process_maintenance_user(app, user, settings, now_ms=now_ms, warning_ms=warning_ms)
        except Exception as error:
            app._log_error(f"Maintenance user error for {user.get('id', 'unknown')}", error)

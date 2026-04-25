# --- Imports ---

import json
import time

from utils_py import (
    format_datetime,
    format_datetime_local_value,
    format_user_name,
    normalize_search,
    parse_datetime_local_value,
    parse_integer,
)


# --- Internal helpers ---

def _now_ms():
    return time.time() * 1000


def _parse_json(value):
    return json.loads(value)


def _format_json(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def _user_search_haystack(user):
    return normalize_search(
        " ".join(
            [
                str(user.get("id", "")),
                user.get("username", ""),
                user.get("firstName", ""),
                user.get("lastName", ""),
                user.get("notes", ""),
            ]
        )
    )


def _is_active_subscription(user, now_ms):
    return bool(user.get("subscriptionUntil") and user["subscriptionUntil"] > now_ms)


def _matches_status_filter(user, status_filter, now_ms):
    is_active = _is_active_subscription(user, now_ms)
    if status_filter == "active":
        return is_active
    if status_filter == "expired":
        return bool(user.get("subscriptionUntil")) and not is_active
    return True


def _build_pending_join_request(form, tz):
    if not form.get("pendingJoinRequestChatId"):
        return None
    return {
        "chatId": form.get("pendingJoinRequestChatId"),
        "createdAt": parse_datetime_local_value(form.get("pendingJoinRequestCreatedAt"), tz) or int(_now_ms()),
        "invite_link": form.get("pendingJoinRequestInviteLink"),
    }


def _render_template_values(template, context):
    rendered = template
    for key, value in context.items():
        placeholder = "{{" + key + "}}"
        rendered = rendered.replace(placeholder, str(value))
    return rendered


def _normalize_channel_id(channel_id):
    normalized = str(channel_id or "").strip()
    if "t.me/" in normalized:
        normalized = normalized.split("t.me/")[-1].split("?")[0].split("/")[0]

    if not normalized.startswith("@") and not normalized.startswith("-100"):
        if normalized.isdigit():
            normalized = f"-100{normalized}"
        else:
            normalized = f"@{normalized}"
    return normalized


# --- View model helpers ---

def get_admin_view_model(app, filters=None):
    """Build the legacy admin/editor view-model without changing its shape."""
    filters = filters or {}
    settings = app.store.get_settings()
    system = app.get_effective_system_settings()
    now_ms = int(_now_ms())
    query = normalize_search(filters.get("q"))
    status_filter = filters.get("status") or "all"

    users = []
    for user in app.store.list_users():
        matches_query = not query or query in _user_search_haystack(user)
        if not _matches_status_filter(user, status_filter, now_ms):
            continue
        if matches_query:
            users.append(user)

    return {
        "stats": app.store.get_dashboard_stats(),
        "settings": settings,
        "system": system,
        "users": users,
        "payments": app.store.get_payments()[:20],
        "auditLog": app.store.get_audit_log(20),
        "timeZone": system["appTimezone"],
        "filters": {"q": filters.get("q", ""), "status": status_filter},
        "stateJson": _format_json(app.store.get_state()),
        "settingsJson": _format_json(settings),
        "templatesJson": _format_json(settings.get("messageTemplates", {})),
    }


def get_user_editor_view_model(app, user_id):
    """Return the legacy user editor payload used by compatibility tooling."""
    user = app.store.get_user(user_id)
    if not user:
        return None

    tz = app.get_effective_system_settings()["appTimezone"]
    pending = user.get("pendingJoinRequest") or {}
    return {
        "user": user,
        "timeZone": tz,
        "rawJson": _format_json(user),
        "form": {
            "id": str(user["id"]),
            "username": user.get("username") or "",
            "firstName": user.get("firstName") or "",
            "lastName": user.get("lastName") or "",
            "languageCode": user.get("languageCode") or "",
            "balanceStars": user.get("balanceStars") or 0,
            "subscriptionUntil": format_datetime_local_value(user.get("subscriptionUntil"), tz),
            "totalSpentStars": user.get("totalSpentStars") or 0,
            "totalPaymentsCount": user.get("totalPaymentsCount") or 0,
            "lastPaymentAt": format_datetime_local_value(user.get("lastPaymentAt"), tz),
            "lastWarningAt": format_datetime_local_value(user.get("lastWarningAt"), tz),
            "lastAccessGrantedAt": format_datetime_local_value(user.get("lastAccessGrantedAt"), tz),
            "lastAccessRevokedAt": format_datetime_local_value(user.get("lastAccessRevokedAt"), tz),
            "channelMemberStatus": user.get("channelMemberStatus") or "unknown",
            "notes": user.get("notes") or "",
            "pendingJoinRequestChatId": pending.get("chatId") or "",
            "pendingJoinRequestCreatedAt": format_datetime_local_value(pending.get("createdAt"), tz),
            "pendingJoinRequestInviteLink": pending.get("inviteLink") or "",
        },
    }


# --- JSON replacement helpers ---

def replace_state_from_json(app, js):
    app.store.replace_state(_parse_json(js))


def replace_settings_from_json(app, js):
    app.store.replace_settings(_parse_json(js))


def replace_templates_from_json(app, js):
    app.store.update_settings({"messageTemplates": _parse_json(js)})


def replace_user_json(app, uid, js):
    app.store.replace_user(uid, _parse_json(js))


# --- User editor helpers ---

def save_user_structured(app, uid, form):
    """Persist user editor fields while preserving the existing stored shape."""
    tz = app.get_effective_system_settings()["appTimezone"]
    app.store.update_user_fields(
        uid,
        {
            "username": form.get("username"),
            "firstName": form.get("firstName"),
            "lastName": form.get("lastName"),
            "balanceStars": parse_integer(form.get("balanceStars"), 0),
            "subscriptionUntil": parse_datetime_local_value(form.get("subscriptionUntil"), tz),
            "notes": form.get("notes"),
            "pendingJoinRequest": _build_pending_join_request(form, tz),
        },
    )


def delete_user(app, uid):
    app.store.delete_user(uid)


# --- Template helpers ---

def get_template_context(app, user_id):
    """Collect the placeholder context consumed by message templates."""
    user = app.store.get_user(user_id)
    settings = app.store.get_settings()
    system = app.get_effective_system_settings()

    return {
        "userId": str(user_id),
        "username": user.get("username") or "",
        "firstName": user.get("firstName") or "",
        "lastName": user.get("lastName") or "",
        "fullName": format_user_name(user),
        "subscriptionUntil": format_datetime(user.get("subscriptionUntil"), system["appTimezone"]),
        "inviteLink": app.store.get_effective_invite_link(app.config.channel_invite_link),
        "supportMention": f"@{settings.get('supportUsername')}" if settings.get("supportUsername") else "\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0435",
        "subscriptionName": settings.get("subscriptionName", "\u041f\u043e\u0434\u043f\u0438\u0441\u043a\u0430"),
        "price": settings.get("subscriptionPriceStars", 0),
    }


def render_message_template(app, name, user_id):
    """Render only known placeholders; unknown placeholders stay unchanged."""
    settings = app.store.get_settings()
    template = settings.get("messageTemplates", {}).get(name) or name
    return _render_template_values(template, get_template_context(app, user_id))


# --- Channel/settings helpers ---

def configure_channel(app, channel_id):
    """Normalize channel input and persist it without requiring a live Telegram client."""
    normalized = _normalize_channel_id(channel_id)
    app.store.update_settings({"channelId": normalized})
    app.refresh_invite_link()


# --- Stats helpers ---

def format_stats_text(app):
    stats = app.store.get_dashboard_stats()
    return (
        f"\U0001f4ca <b>\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430 \u0441\u0438\u0441\u0442\u0435\u043c\u044b</b>\n\n"
        f"\u042e\u0437\u0435\u0440\u043e\u0432 \u0432\u0441\u0435\u0433\u043e: {stats['totalUsers']}\n"
        f"\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0445: {stats['activeSubscriptions']}\n"
        f"\u0418\u0441\u0442\u0435\u043a\u0448\u0438\u0445: {stats['expiredSubscriptions']}\n"
        f"\u041e\u0436\u0438\u0434\u0430\u044e\u0442 \u0432\u0445\u043e\u0434: {stats['pendingJoinRequests']}\n"
        f"\u0414\u043e\u0445\u043e\u0434: {stats['revenueStars']} Stars\n"
        f"\u0411\u0430\u043b\u0430\u043d\u0441 \u044e\u0437\u0435\u0440\u043e\u0432: {stats['totalBalanceStars']} Stars"
    )


def get_dashboard_stats_extended(app):
    """Extend dashboard stats with 30-day revenue while preserving the existing payload."""
    stats = app.store.get_dashboard_stats()
    month_ago = _now_ms() - (30 * 24 * 3600 * 1000)

    revenue_month = 0
    for payment in app.store.get_payments():
        if payment.get("paidAt", 0) > month_ago:
            revenue_month += payment.get("totalAmount") or 0

    stats["revenueMonth"] = revenue_month
    return stats

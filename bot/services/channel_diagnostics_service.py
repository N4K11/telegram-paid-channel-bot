from bot import logging_config

import re


TOKEN_PATTERN = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b")
PRIVATE_INVITE_PATTERN = re.compile(r"https://t\.me/\+[A-Za-z0-9_-]+")


def _sanitize_error_text(message):
    text = str(message or "").strip()
    if not text:
        return ""
    text = TOKEN_PATTERN.sub("<redacted-token>", text)
    text = PRIVATE_INVITE_PATTERN.sub("<redacted-invite-link>", text)
    return text


def _classify_member_error(message):
    lower = str(message or "").lower()
    if "kicked from the channel chat" in lower or "bot was kicked" in lower:
        return "bot_kicked"
    if "not a member of the channel chat" in lower or "bot is not a member" in lower:
        return "bot_not_in_channel"
    if "chat not found" in lower or "invalid chat id" in lower:
        return "invalid_channel_id"
    return "telegram_api_error"


def _admin_permission(member, field_name):
    status = member.get("status")
    if status == "creator":
        return True
    return bool(member.get(field_name))


def _initial_result(app):
    system = app.get_effective_system_settings()
    settings = app.store.get_settings()
    channel_id = system.get("channelId") or ""
    return {
        "channelId": channel_id,
        "channelConfigured": bool(channel_id),
        "bot": None,
        "channelAccessOk": False,
        "memberStatus": "unknown",
        "isAdmin": False,
        "canInviteUsers": False,
        "canApproveJoinRequests": False,
        "canRestrictMembers": False,
        "manualInviteConfigured": bool(app.store.get_effective_invite_link(app.config.channel_invite_link)),
        "autoCreateInviteLink": bool(system.get("autoCreateInviteLink")),
        "inviteFlowAvailable": False,
        "error": "",
        "errorKind": "",
        "warnings": [],
        "notes": [],
    }


def run_channel_diagnostics(app):
    result = _initial_result(app)
    if not result["channelConfigured"]:
        result["warnings"].append("CHANNEL_ID не настроен.")
        return result

    try:
        bot_info = app.store.get_meta().get("botInfo") or app.get_telegram().get_me()
        result["bot"] = {
            "id": bot_info.get("id"),
            "username": bot_info.get("username") or "",
        }
    except Exception as error:
        result["error"] = _sanitize_error_text(error)
        result["errorKind"] = "get_me_failed"
        result["warnings"].append("Не удалось получить информацию о боте через Telegram API.")
        app.log_event(
            "channel_diagnostics_failed",
            error_kind=result["errorKind"],
            channel_id=result["channelId"],
            error=result["error"],
        )
        return result

    try:
        member = app.get_telegram().get_chat_member(result["channelId"], result["bot"]["id"])
    except Exception as error:
        result["error"] = _sanitize_error_text(error)
        result["errorKind"] = _classify_member_error(error)
        if result["errorKind"] == "bot_kicked":
            result["warnings"].append("Бот удалён из канала.")
        elif result["errorKind"] == "bot_not_in_channel":
            result["warnings"].append("Бот не состоит в канале.")
        elif result["errorKind"] == "invalid_channel_id":
            result["warnings"].append("CHANNEL_ID невалиден или канал не найден.")
        else:
            result["warnings"].append("Telegram API вернул ошибку при проверке доступа к каналу.")
        app.log_event(
            "channel_diagnostics_failed",
            error_kind=result["errorKind"],
            channel_id=result["channelId"],
            error=result["error"],
        )
        return result

    result["channelAccessOk"] = True
    result["memberStatus"] = member.get("status") or "unknown"
    result["isAdmin"] = result["memberStatus"] in {"administrator", "creator"}
    result["canInviteUsers"] = _admin_permission(member, "can_invite_users")
    result["canApproveJoinRequests"] = result["canInviteUsers"]
    result["canRestrictMembers"] = _admin_permission(member, "can_restrict_members")
    result["inviteFlowAvailable"] = result["manualInviteConfigured"] or (
        result["autoCreateInviteLink"] and result["canInviteUsers"]
    )

    if not result["isAdmin"]:
        result["warnings"].append("Бот не является администратором канала.")
    if result["isAdmin"] and not result["canInviteUsers"]:
        result["warnings"].append("У бота нет права создавать invite links / approve join requests.")
    if result["isAdmin"] and not result["canRestrictMembers"]:
        result["warnings"].append("У бота нет права restrict/ban users для revoke flow.")
    if not result["inviteFlowAvailable"]:
        result["warnings"].append("Invite-link flow сейчас недоступен.")

    result["notes"].append("Approve join requests в Bot API зависит от права can_invite_users.")
    if result["manualInviteConfigured"]:
        result["notes"].append("В настройках уже есть ручная ссылка канала.")
    if result["autoCreateInviteLink"]:
        result["notes"].append("Автосоздание invite link включено.")
    else:
        result["notes"].append("Автосоздание invite link выключено.")
    return result


def format_channel_diagnostics(result):
    lines = [
        "<b>📡 Диагностика канала</b>",
        "",
        (
            f"✅ CHANNEL_ID прочитан: <code>{result['channelId']}</code>"
            if result.get("channelConfigured")
            else "❌ CHANNEL_ID не настроен"
        ),
    ]

    bot = result.get("bot")
    if bot:
        username = f"@{bot['username']}" if bot.get("username") else "без username"
        lines.append(f"🤖 Бот: {username} (ID <code>{bot['id']}</code>)")
    else:
        lines.append("❌ Информация о боте недоступна")

    lines.extend(
        [
            (
                f"✅ Доступ к каналу подтверждён (status: <code>{result['memberStatus']}</code>)"
                if result.get("channelAccessOk")
                else "❌ Доступ к каналу не подтверждён"
            ),
            "✅ Бот является администратором канала" if result.get("isAdmin") else "❌ Бот не администратор канала",
            (
                "✅ Есть право создавать invite links / approve join requests"
                if result.get("canInviteUsers")
                else "❌ Нет права создавать invite links / approve join requests"
            ),
            (
                "✅ Есть право restrict/ban users для revoke flow"
                if result.get("canRestrictMembers")
                else "❌ Нет права restrict/ban users для revoke flow"
            ),
            (
                "✅ Ручная ссылка канала настроена"
                if result.get("manualInviteConfigured")
                else "❌ Ручная ссылка канала не настроена"
            ),
            (
                "✅ Автосоздание invite link включено"
                if result.get("autoCreateInviteLink")
                else "❌ Автосоздание invite link выключено"
            ),
            (
                "✅ Invite-link flow доступен"
                if result.get("inviteFlowAvailable")
                else "❌ Invite-link flow недоступен"
            ),
        ]
    )

    error = result.get("error")
    if error:
        lines.extend(
            [
                "",
                "<b>Ошибка Telegram API</b>",
                error,
            ]
        )

    warnings = result.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("<b>Что требует внимания</b>")
        lines.extend(f"• {warning}" for warning in warnings)

    notes = result.get("notes") or []
    if notes:
        lines.append("")
        lines.append("<b>Примечания</b>")
        lines.extend(f"• {note}" for note in notes)

    return "\n".join(lines)


from utils_py import parse_integer


def _set_target_state_and_render(handler, user_id, state, target_id, prompt):
    handler.fsm.set_state(user_id, state)
    handler.fsm.set_data(user_id, "target_user_id", target_id)
    handler._render_input_request(user_id, prompt)


def _handle_positive_setting_input(handler, user_id, text, setting_key, notice_template, invalid_text):
    value = parse_integer(text, -1)
    if value >= 1:
        handler.bot.update_settings({setting_key: value})
        handler.fsm.clear(user_id)
        handler._render_settings(user_id, notice=notice_template.format(value=value))
        return
    handler._render_input_request(user_id, invalid_text)


def _handle_template_save(handler, user_id, key, text):
    top_level_keys = {"welcomeText", "subscriptionName", "subscriptionDescription", "supportUsername"}
    if key in top_level_keys:
        handler.bot.update_settings({key: text})
    else:
        handler.bot.update_settings({"messageTemplates": {key: text}})
    handler.fsm.clear(user_id)
    handler._render_templates_menu(user_id, notice="Текст обновлен")


def _require_admin(handler, callback_query):
    if handler.bot.is_authorized_admin(callback_query["from"]):
        return True
    handler.bot.get_telegram().answer_callback_query(callback_query["id"], "Нет доступа")
    return False


def handle_callback(handler, callback_query):
    user_id = callback_query["from"]["id"]
    data = callback_query["data"]

    if not _require_admin(handler, callback_query):
        return

    if data == "admin:menu":
        handler.fsm.clear(user_id)
        handler._render_main(user_id)
    elif data == "admin:payment_anomalies":
        handler.fsm.clear(user_id)
        handler._render_payment_anomalies(user_id)
    elif data == "admin:stats":
        handler._render_stats(user_id)
    elif data == "admin:settings":
        handler.fsm.clear(user_id)
        handler._render_settings(user_id)
    elif data == "admin:refresh_invite":
        try:
            link = handler.bot.refresh_invite_link()
            handler._render_main(user_id, notice=f"Ссылка обновлена: {link}")
        except Exception as error:
            handler._render_main(user_id, notice=f"Ошибка: {error}")
    elif data == "admin:users:0":
        handler.fsm.set_data(user_id, "user_filter", "all")
        handler._render_users(user_id, 0)
    elif data.startswith("admin:users:"):
        page = parse_integer(data.split(":")[-1], 0)
        handler._render_users(user_id, page)
    elif data.startswith("admin:filter:"):
        handler.fsm.set_data(user_id, "user_filter", data.split(":")[-1])
        handler._render_users(user_id, 0)
    elif data.startswith("admin:user:"):
        target_id = parse_integer(data.split(":")[-1])
        handler._render_user_details(user_id, target_id)
    elif data == "admin:templates:menu":
        handler.fsm.clear(user_id)
        handler._render_templates_menu(user_id)
    elif data.startswith("admin:templates:edit:"):
        handler._handle_template_edit_trigger(user_id, data.split(":")[-1])
    elif data.startswith("admin:broadcast:"):
        handler._handle_broadcast_trigger(user_id, data)
    elif data.startswith("admin:input:"):
        handler._handle_input_trigger(user_id, data)
    elif data == "admin:toggle:recurring":
        settings = handler.store.get_settings()
        handler.bot.update_settings({"recurringPaymentsEnabled": not settings.get("recurringPaymentsEnabled")})
        handler._render_settings(user_id, notice="Recurring переключен")
    elif data == "admin:toggle:autoinvite":
        system = handler.bot.get_effective_system_settings()
        handler.bot.update_settings({"autoCreateInviteLink": not system["autoCreateInviteLink"]})
        handler._render_settings(user_id, notice="Auto-invite переключен")
    elif data.startswith("admin:approve:"):
        target_id = parse_integer(data.split(":")[-1])
        if handler.bot.approve_pending_request(target_id, force=True):
            handler._render_user_details(user_id, target_id, notice="Заявка одобрена")
        else:
            handler._render_user_details(
                user_id,
                target_id,
                notice="Не удалось одобрить. Возможно, заявки нет или бот не админ.",
            )
    elif data.startswith("admin:revoke:"):
        target_id = parse_integer(data.split(":")[-1])
        handler.bot.revoke_user_subscription(target_id, "admin_revoke")
        handler._render_user_details(user_id, target_id, notice="Доступ отозван")

    handler.bot.get_telegram().answer_callback_query(callback_query["id"])


def handle_text(handler, message):
    user_id = message["from"]["id"]
    state = handler.fsm.get_state(user_id)
    if not state or not state.startswith("admin:wait:"):
        return False

    try:
        handler.bot.get_telegram().delete_message(user_id, message["message_id"])
    except Exception:
        pass

    text = message.get("text", "").strip()
    if not text:
        return True

    if state == "admin:wait:price":
        _handle_positive_setting_input(
            handler,
            user_id,
            text,
            "subscriptionPriceStars",
            "Цена изменена на {value}",
            "Введите корректную цену (число >= 1)",
        )
    elif state == "admin:wait:days":
        _handle_positive_setting_input(
            handler,
            user_id,
            text,
            "subscriptionDurationDays",
            "Срок изменен на {value}",
            "Введите число дней (>= 1)",
        )
    elif state == "admin:wait:warning":
        _handle_positive_setting_input(
            handler,
            user_id,
            text,
            "warningDays",
            "Срок предупреждения изменен на {value}",
            "Введите число (>= 1)",
        )
    elif state == "admin:wait:channel":
        try:
            handler.bot.configure_channel(text)
            handler.fsm.clear(user_id)
            handler._render_settings(user_id, notice="Канал обновлен")
        except Exception as error:
            handler._render_input_request(user_id, f"Ошибка: {error}")
    elif state == "admin:wait:grant":
        target_id = handler.fsm.get_data(user_id, "target_user_id")
        days = parse_integer(text, -1)
        if days >= 1:
            handler.bot.grant_user_subscription(target_id, days)
            handler.fsm.clear(user_id)
            handler._render_user_details(user_id, target_id, notice=f"Выдано {days} дн.")
        else:
            handler._render_input_request(user_id, "Введите число дней")
    elif state == "admin:wait:balance":
        target_id = handler.fsm.get_data(user_id, "target_user_id")
        amount = parse_integer(text, 0)
        handler.bot.adjust_user_balance(target_id, amount)
        handler.fsm.clear(user_id)
        handler._render_user_details(user_id, target_id, notice=f"Баланс изменен на {amount}")
    elif state == "admin:wait:note":
        target_id = handler.fsm.get_data(user_id, "target_user_id")
        handler.bot.set_user_notes(target_id, text)
        handler.fsm.clear(user_id)
        handler._render_user_details(user_id, target_id, notice="Заметка сохранена")
    elif state == "admin:wait:msg":
        target_id = handler.fsm.get_data(user_id, "target_user_id")
        if handler.bot.send_admin_message(target_id, text):
            handler.fsm.clear(user_id)
            handler._render_user_details(user_id, target_id, notice="Сообщение отправлено")
        else:
            handler._render_input_request(user_id, "Сообщение не может быть пустым")
    elif state == "admin:wait:broadcast":
        scope = handler.fsm.get_data(user_id, "broadcast_scope") or "all"
        count = handler.bot.broadcast_users(scope, text)
        handler.fsm.clear(user_id)
        handler._render_main(user_id, notice=f"Рассылка ({scope}) отправлена {count} пользователям")
    elif state == "admin:wait:search_user":
        handler.fsm.clear(user_id)
        if text:
            handler.fsm.set_data(user_id, "user_search_query", text)
        handler._render_users(user_id, 0)
    elif state == "admin:wait:template":
        key = handler.fsm.get_data(user_id, "template_key")
        _handle_template_save(handler, user_id, key, text)

    return True


def handle_input_trigger(handler, user_id, data):
    parts = data.split(":")
    key = parts[2]

    if key == "price":
        handler.fsm.set_state(user_id, "admin:wait:price")
        handler._render_input_request(user_id, "💰 Введите новую цену подписки (в Stars):")
    elif key == "days":
        handler.fsm.set_state(user_id, "admin:wait:days")
        handler._render_input_request(user_id, "⏳ Введите длительность подписки (в днях):")
    elif key == "warning":
        handler.fsm.set_state(user_id, "admin:wait:warning")
        handler._render_input_request(user_id, "🔔 За сколько дней присылать предупреждение?")
    elif key == "channel":
        handler.fsm.set_state(user_id, "admin:wait:channel")
        handler._render_input_request(user_id, "📡 Введите ID или username канала:")
    elif key == "support":
        handler.fsm.set_state(user_id, "admin:wait:template")
        handler.fsm.set_data(user_id, "template_key", "supportUsername")
        handler._render_input_request(user_id, "🆘 Введите username поддержки (без @):")
    elif key == "grant":
        target_id = parse_integer(parts[-1])
        _set_target_state_and_render(handler, user_id, "admin:wait:grant", target_id, f"➕ Сколько дней выдать ID {target_id}?")
    elif key == "balance":
        target_id = parse_integer(parts[-1])
        _set_target_state_and_render(handler, user_id, "admin:wait:balance", target_id, f"💰 Сколько Stars добавить ID {target_id}?")
    elif key == "note":
        target_id = parse_integer(parts[-1])
        _set_target_state_and_render(handler, user_id, "admin:wait:note", target_id, f"📝 Заметка для ID {target_id}:")
    elif key == "msg":
        target_id = parse_integer(parts[-1])
        _set_target_state_and_render(handler, user_id, "admin:wait:msg", target_id, f"✉️ Текст сообщения для {target_id}:")
    elif key == "search_user":
        handler.fsm.set_state(user_id, "admin:wait:search_user")
        handler._render_input_request(user_id, "🔍 Введите ID или имя для поиска:")


def handle_broadcast_trigger(handler, user_id, data):
    scope = data.split(":")[-1]
    if scope == "menu":
        text, markup = handler.ui.get_admin_broadcast_menu()
        handler.bot.render_panel(user_id, text, markup, "admin:broadcast:menu")
        return

    handler.fsm.set_state(user_id, "admin:wait:broadcast")
    handler.fsm.set_data(user_id, "broadcast_scope", scope)
    handler._render_input_request(user_id, f"📢 Введите текст рассылки ({scope}):")


def handle_template_edit_trigger(handler, user_id, key):
    handler.fsm.set_state(user_id, "admin:wait:template")
    handler.fsm.set_data(user_id, "template_key", key)
    settings = handler.store.get_settings()
    text, markup = handler.ui.get_admin_template_editor(key, settings.get(key))
    handler.bot.render_panel(user_id, text, markup, f"admin:templates:edit:{key}")

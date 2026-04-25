from bot.services import access_service
from bot.services import payment_service
from bot.services import promo_service


def dispatch_update(app, update):
    if update.get("message"):
        return app.handle_message(update["message"])
    if update.get("callback_query"):
        return app.handle_callback_query(update["callback_query"])
    if update.get("pre_checkout_query"):
        return app.handle_pre_checkout_query(update["pre_checkout_query"])
    if update.get("chat_join_request"):
        return app.handle_chat_join_request(update["chat_join_request"])
    return None


def dispatch_message(app, message):
    user_id = app._ensure_user_context(message.get("from"))
    if user_id is None:
        return None

    if message.get("successful_payment"):
        return dispatch_successful_payment(app, message)

    text = message.get("text", "").strip()
    if not text:
        return None

    if app.admin_handler.handle_text(message):
        return None

    parts = text.split(None, 1)
    command = parts[0]
    params = parts[1] if len(parts) > 1 else None

    if command in app.ADMIN_COMMANDS:
        return dispatch_admin_command(app, message, command, params or "")

    return dispatch_user_command(app, message, command, params)


def dispatch_callback_query(app, callback_query):
    app._ensure_user_context(callback_query["from"])
    data = callback_query.get("data", "")

    if data.startswith("admin:"):
        return app.admin_handler.handle_callback(callback_query)
    return app.user_handler.handle_callback(callback_query)


def _parse_limit_or_error(app, chat_id, args):
    limit = 20
    if args.strip():
        try:
            limit = int(args.strip())
        except ValueError:
            app.get_telegram().send_message(chat_id, "Использование: /admin_payment_anomalies [LIMIT]")
            return None
    return max(1, min(limit, 100))


def _parse_recovery_args_or_error(app, chat_id, args):
    parts = args.split(None, 2)
    if len(parts) < 3:
        app.get_telegram().send_message(chat_id, "Использование: /admin_recover_payment USER_ID DAYS REASON")
        return None

    try:
        target_id = int(parts[0])
        days = int(parts[1])
    except ValueError:
        app.get_telegram().send_message(chat_id, "USER_ID и DAYS должны быть числами.")
        return None

    if days < 1:
        app.get_telegram().send_message(chat_id, "DAYS должен быть числом не меньше 1.")
        return None

    return target_id, days, parts[2]


def _parse_promo_create_args_or_error(app, chat_id, args):
    parsed = promo_service.parse_admin_create_args(args)
    if parsed is not None:
        return parsed
    app.get_telegram().send_message(
        chat_id,
        "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /admin_promo_create CODE TYPE VALUE LIMIT\nTYPE: free_days | discount_percent | discount_stars | fixed_price",
    )
    return None


def dispatch_admin_command(app, message, command, args):
    user = message["from"]
    chat_id = user["id"]

    if command == "/admin_login":
        return app._handle_admin_login(user, chat_id, args)

    if command == "/admin_logout":
        return app._handle_admin_logout(user, chat_id)

    if not app.is_authorized_admin(user):
        return app.get_telegram().send_message(chat_id, "🔒 Доступ ограничен. Используйте /admin_login")

    if command == "/admin_payment_diag":
        target_id = args.strip()
        if not target_id:
            return app.get_telegram().send_message(chat_id, "Использование: /admin_payment_diag USER_ID")
        return app.admin_handler._render_payment_diagnostics(chat_id, target_id)

    if command == "/admin_channel_check":
        return app.admin_handler._render_channel_diagnostics(chat_id)

    if command == "/admin_health":
        return app.admin_handler._render_health(chat_id)

    if command == "/admin_revenue":
        return app.admin_handler._render_revenue(chat_id)

    if command == "/admin_activity":
        return app.admin_handler._render_activity(chat_id)

    if command == "/admin_payment_anomalies":
        limit = _parse_limit_or_error(app, chat_id, args)
        if limit is None:
            return None
        return app.admin_handler._render_payment_anomalies(chat_id, limit)

    if command == "/admin_promo_create":
        parsed = _parse_promo_create_args_or_error(app, chat_id, args)
        if parsed is None:
            return None
        code, promo_type, value, limit = parsed
        result = app.store.create_promo_code(code, promo_type, value, limit, admin_id=user["id"])
        return app.get_telegram().send_message(chat_id, promo_service.format_admin_create_result(result))

    if command == "/admin_promo_disable":
        code = promo_service.normalize_promo_code(args.strip())
        if not code:
            return app.get_telegram().send_message(chat_id, "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /admin_promo_disable CODE")
        result = app.store.disable_promo_code(code, admin_id=user["id"])
        return app.get_telegram().send_message(chat_id, promo_service.format_admin_disable_result(result, code))

    if command == "/admin_promo_stats":
        code = args.strip()
        if not code:
            return app.get_telegram().send_message(chat_id, "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /admin_promo_stats CODE")
        result = promo_service.get_promo_stats(app.store, code)
        return app.get_telegram().send_message(chat_id, promo_service.format_promo_stats(result))

    if command == "/admin_recover_payment":
        parsed = _parse_recovery_args_or_error(app, chat_id, args)
        if parsed is None:
            return None

        target_id, days, reason = parsed
        recovered = app.manual_recover_payment_access(user["id"], target_id, days, reason)
        if not recovered:
            return app.get_telegram().send_message(chat_id, "Пользователь не найден.")

        return app.admin_handler._render_user_details(
            chat_id,
            target_id,
            notice="Ручное восстановление доступа выполнено. Статистика оплат не изменялась.",
        )

    return app._dispatch_admin_command(chat_id, command)


def dispatch_user_command(app, message, command, params):
    return app.user_handler.handle_command(message, command, params)


def dispatch_pre_checkout(app, pre_checkout_query):
    return payment_service.handle_pre_checkout(app, pre_checkout_query)


def dispatch_successful_payment(app, message):
    return payment_service.handle_successful_payment(app, message)


def dispatch_chat_join_request(app, join_request):
    return access_service.handle_chat_join_request(app, join_request)

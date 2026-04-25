from bot.handlers import user_render


def _ensure_user_from_message(handler, message):
    user = message.get("from") or {}
    if user:
        handler.store.ensure_user(user)
    return user.get("id")


def _ensure_user_from_callback(handler, callback_query):
    user = callback_query.get("from") or {}
    if user:
        handler.store.ensure_user(user)
    return user.get("id")


def _get_user_id_from_message(message):
    user = message.get("from") or {}
    return user.get("id")


def _get_user_id_from_callback(callback_query):
    user = callback_query.get("from") or {}
    return user.get("id")


def handle_callback(handler, callback_query):
    user_id = _ensure_user_from_callback(handler, callback_query)
    data = callback_query.get("data")

    if data == "panel:main":
        user_render.render_main_menu(handler, user_id, callback_query=callback_query)
    elif data == "buy":
        user_render.render_buy_invoice_notice(handler, user_id, callback_query=callback_query)
    elif data == "join":
        user_render.render_join_link(handler, user_id, callback_query=callback_query)
    elif data == "user:help":
        user_render.render_help(handler, user_id, callback_query=callback_query)
    elif data == "buy_balance":
        result = handler.store.purchase_with_balance(user_id, handler.store.get_settings())
        user_render.render_buy_balance_result(handler, user_id, result, callback_query=callback_query)

    return handler.bot.get_telegram().answer_callback_query(callback_query["id"])


def handle_command(handler, message, command, parameter):
    user_id = _ensure_user_from_message(handler, message)

    if command == "/start":
        if parameter == "buy":
            return handler.bot.send_invoice(user_id)
        return user_render.render_main_menu(handler, user_id, force_new=True)

    if command == "/buy":
        return handler.bot.send_invoice(user_id)

    if command == "/buy_balance":
        return handle_callback(handler, {"from": {"id": user_id}, "data": "buy_balance", "id": "0"})

    if command == "/status":
        return user_render.render_main_menu(handler, user_id, force_new=True)

    if command == "/help":
        return user_render.render_help(handler, user_id, force_new=True)

    return user_render.render_main_menu(handler, user_id, force_new=True)

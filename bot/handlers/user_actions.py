from bot.handlers import user_render
from bot.services import plan_service


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
    settings = handler.store.get_settings()
    enabled_plans = plan_service.get_enabled_plans(settings)

    if data == "panel:main":
        user_render.render_main_menu(handler, user_id, callback_query=callback_query)
    elif data == "buy":
        if not enabled_plans:
            user_render.render_main_menu(handler, user_id, notice="Сейчас нет доступных тарифов.", callback_query=callback_query)
        elif len(enabled_plans) > 1:
            user_render.render_plan_picker(
                handler,
                user_id,
                enabled_plans,
                purchase_mode="invoice",
                callback_query=callback_query,
            )
        else:
            user_render.render_buy_invoice_notice(handler, user_id, callback_query=callback_query)
    elif data.startswith("buy:plan:"):
        plan_id = data.split(":", 2)[2]
        plan = plan_service.get_plan(settings, plan_id)
        if not plan:
            user_render.render_main_menu(handler, user_id, notice="Тариф недоступен.", callback_query=callback_query)
        else:
            user_render.render_buy_invoice_notice(handler, user_id, callback_query=callback_query, plan_id=plan_id)
    elif data == "join":
        user_render.render_join_link(handler, user_id, callback_query=callback_query)
    elif data == "user:help":
        user_render.render_help(handler, user_id, callback_query=callback_query)
    elif data == "buy_balance":
        affordable_plans = [plan for plan in enabled_plans if (handler.store.get_user(user_id) or {}).get("balanceStars", 0) >= plan["priceStars"]]
        if not enabled_plans:
            user_render.render_main_menu(handler, user_id, notice="Сейчас нет доступных тарифов.", callback_query=callback_query)
        elif len(enabled_plans) > 1:
            user_render.render_plan_picker(
                handler,
                user_id,
                enabled_plans,
                purchase_mode="balance",
                callback_query=callback_query,
                notice=None if affordable_plans else "На балансе недостаточно Stars для любого тарифа.",
            )
        else:
            result = handler.store.purchase_with_balance(
                user_id,
                plan_service.apply_plan_to_settings(settings, enabled_plans[0]),
            )
            user_render.render_buy_balance_result(handler, user_id, result, callback_query=callback_query)
    elif data.startswith("buy_balance:plan:"):
        plan_id = data.split(":", 2)[2]
        plan = plan_service.get_plan(settings, plan_id)
        if not plan:
            user_render.render_main_menu(handler, user_id, notice="Тариф недоступен.", callback_query=callback_query)
        else:
            result = handler.store.purchase_with_balance(
                user_id,
                plan_service.apply_plan_to_settings(settings, plan),
            )
            user_render.render_buy_balance_result(handler, user_id, result, callback_query=callback_query)

    return handler.bot.get_telegram().answer_callback_query(callback_query["id"])


def handle_command(handler, message, command, parameter):
    user_id = _ensure_user_from_message(handler, message)

    if command == "/start":
        if parameter == "buy":
            return handler.bot.send_invoice(user_id)
        return user_render.render_main_menu(handler, user_id, force_new=True)

    if command == "/buy":
        settings = handler.store.get_settings()
        enabled_plans = plan_service.get_enabled_plans(settings)
        if not enabled_plans:
            return user_render.render_main_menu(handler, user_id, notice="Сейчас нет доступных тарифов.", force_new=True)
        if len(enabled_plans) > 1:
            return user_render.render_plan_picker(
                handler,
                user_id,
                enabled_plans,
                purchase_mode="invoice",
            )
        return handler.bot.send_invoice(user_id)

    if command == "/buy_balance":
        settings = handler.store.get_settings()
        enabled_plans = plan_service.get_enabled_plans(settings)
        if not enabled_plans:
            return user_render.render_main_menu(handler, user_id, notice="Сейчас нет доступных тарифов.", force_new=True)
        if len(enabled_plans) > 1:
            return user_render.render_plan_picker(
                handler,
                user_id,
                enabled_plans,
                purchase_mode="balance",
            )
        result = handler.store.purchase_with_balance(
            user_id,
            plan_service.apply_plan_to_settings(settings, enabled_plans[0]),
        )
        return user_render.render_buy_balance_result(handler, user_id, result)

    if command == "/status":
        return user_render.render_main_menu(handler, user_id, force_new=True)

    if command == "/help":
        return user_render.render_help(handler, user_id, force_new=True)

    return user_render.render_main_menu(handler, user_id, force_new=True)

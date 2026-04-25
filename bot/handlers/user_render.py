def render_main_menu(handler, user_id, notice=None, callback_query=None, force_new=False):
    return handler.bot.send_main_menu(
        user_id,
        notice=notice,
        callback_query=callback_query,
        force_new=force_new,
    )


def render_help(handler, user_id, callback_query=None, force_new=False):
    return handler.bot.send_user_help(
        user_id,
        callback_query=callback_query,
        force_new=force_new,
    )


def render_join_link(handler, user_id, callback_query=None):
    return handler.bot.send_join_link(user_id, callback_query=callback_query)


def render_buy_invoice_notice(handler, user_id, callback_query=None):
    handler.bot.send_invoice(user_id)
    return render_main_menu(
        handler,
        user_id,
        notice="Счёт на оплату отправлен отдельным сообщением.",
        callback_query=callback_query,
    )


def render_buy_balance_result(handler, user_id, result, callback_query=None):
    if not result["ok"]:
        return render_main_menu(
            handler,
            user_id,
            notice="❌ На балансе недостаточно Stars.",
            callback_query=callback_query,
        )

    handler.bot.approve_pending_request(user_id)
    subscription_until = handler.bot.get_template_context(user_id)["subscriptionUntil"]
    return render_main_menu(
        handler,
        user_id,
        notice=f"✅ Подписка успешно оплачена с баланса и продлена до <b>{subscription_until}</b>.",
        callback_query=callback_query,
    )

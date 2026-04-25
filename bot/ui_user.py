from bot.services import plan_service
from bot.services import subscription_view_service
from bot.ui_common import callback_button, inline_keyboard, url_button


def get_main_menu(context):
    settings = context["settings"]
    user = context["user"] or {}
    is_active = context["is_active"]
    effective_invite_link = context["effective_invite_link"]
    enabled_plans = plan_service.get_enabled_plans(settings)

    text = [
        f"<b>{settings['subscriptionName']}</b>",
        settings.get("welcomeText") or "",
        "",
        "<b>Тариф</b>" if len(enabled_plans) <= 1 else "<b>Тарифы</b>",
    ]

    if len(enabled_plans) <= 1:
        plan = enabled_plans[0] if enabled_plans else plan_service.get_default_plan(settings)
        if plan:
            text.extend(
                [
                    f"Цена: <b>{plan['priceStars']} Stars</b>",
                    f"Срок: <b>{plan_service.format_plan_duration(plan)}</b>",
                    "",
                ]
            )
    else:
        for plan in enabled_plans:
            text.append(
                f"• <b>{plan['title']}</b> — {plan['priceStars']} Stars / {plan_service.format_plan_duration(plan)}"
            )
        text.append("")

    text.append(f"Баланс: <b>{user.get('balanceStars', 0)} Stars</b>.")
    text.extend(subscription_view_service.build_main_menu_status_lines(context))

    if context.get("notice"):
        text.append(f"\n💡 {context['notice']}")

    buttons = [
        [callback_button("🚀 Продлить доступ" if is_active else "💳 Купить доступ", "buy")],
    ]

    row2 = []
    if is_active and effective_invite_link:
        row2.append(url_button("🔗 Открыть канал", effective_invite_link))
    else:
        row2.append(callback_button("📥 Получить ссылку", "join"))

    row2.append(callback_button("❓ Помощь", "user:help"))
    buttons.append(row2)

    if any((user.get("balanceStars") or 0) >= plan["priceStars"] for plan in enabled_plans):
        buttons.append([callback_button("✨ Оплатить с баланса", "buy_balance")])

    utils = []
    support_username = settings.get("supportUsername") or ""
    if support_username:
        utils.append(url_button("🆘 Поддержка", f"https://t.me/{support_username.lstrip('@')}"))

    if context.get("is_admin"):
        utils.append(callback_button("⚙️ Админка", "admin:menu"))

    if utils:
        buttons.append(utils)

    return "\n".join(text), {"inline_keyboard": buttons}


def get_user_help(support_username):
    return subscription_view_service.build_help_text(support_username), inline_keyboard(
        [callback_button("🔙 Назад", "panel:main")]
    )


def get_plan_picker(settings, plans, purchase_mode="invoice", balance_stars=0):
    text = [
        "<b>Выберите тариф</b>" if purchase_mode == "invoice" else "<b>Выберите тариф для оплаты с баланса</b>",
        "",
    ]
    buttons = []

    for plan in plans:
        text.append(
            f"• <b>{plan['title']}</b> — {plan['priceStars']} Stars / {plan_service.format_plan_duration(plan)}"
        )
        callback_data = f"buy:plan:{plan['id']}" if purchase_mode == "invoice" else f"buy_balance:plan:{plan['id']}"
        label = plan_service.format_plan_label(plan)
        if purchase_mode == "balance" and balance_stars:
            label = f"{label} · баланс {balance_stars}"
        buttons.append([callback_button(label, callback_data)])

    buttons.append([callback_button("🔙 Назад", "panel:main")])
    return "\n".join(text), {"inline_keyboard": buttons}

from utils_py import format_datetime

from bot.ui_common import callback_button, inline_keyboard, url_button


def get_main_menu(context):
    settings = context["settings"]
    user = context["user"]
    is_active = context["is_active"]
    effective_invite_link = context["effective_invite_link"]

    text = [
        f"<b>{settings['subscriptionName']}</b>",
        settings.get("welcomeText") or "",
        "",
        "<b>Тариф</b>",
        f"Цена: <b>{settings['subscriptionPriceStars']} Stars</b>",
        f"Срок: <b>{settings['subscriptionDurationDays']} дней</b>",
        "",
        f"Баланс: <b>{user.get('balanceStars', 0)} Stars</b>.",
    ]

    if is_active:
        text.append(
            f"Доступ активен до <b>{format_datetime(user.get('subscriptionUntil'), context['system']['appTimezone'])}</b>."
        )
    else:
        text.append("Подписка сейчас <b>не активна</b>.")

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

    if (user.get("balanceStars") or 0) >= settings["subscriptionPriceStars"]:
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
    text = [
        "<b>📖 Справка по боту</b>",
        "",
        "1. <b>Как купить доступ?</b> Нажмите кнопку «Купить доступ» и оплатите счет через Telegram Stars.",
        "2. <b>Как зайти в канал?</b> После оплаты появится кнопка «Открыть канал». Также вы можете нажать «Получить ссылку», если уже оплатили.",
        "3. <b>Если не заходит?</b> Бот автоматически одобряет заявки. Если возникла проблема, напишите в поддержку.",
        "",
        f"По всем вопросам: @{support_username.lstrip('@')}" if support_username else "",
    ]
    return "\n".join(text), inline_keyboard([callback_button("🔙 Назад", "panel:main")])

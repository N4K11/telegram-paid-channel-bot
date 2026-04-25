import time

from utils_py import format_datetime, format_user_name

from bot.ui_common import callback_button, inline_keyboard


def get_admin_main(stats, system, invite_link, notice=None):
    text = [
        "<b>⚙️ Админ-панель</b>",
        f"Юзеров: <b>{stats['totalUsers']}</b> | Активных: <b>{stats['activeSubscriptions']}</b>",
        f"В канале: <b>{stats['channelMembers']}</b> | Ожидают: <b>{stats['pendingJoinRequests']}</b>",
        f"Доход всего: <b>{stats['revenueStars']} ⭐</b>",
        f"Доход за 30 дней: <b>{stats.get('revenueMonth', 0)} ⭐</b>",
        "",
        f"Канал ID: <code>{system['channelId'] or 'не задан'}</code>",
    ]
    if notice:
        text.append(f"\n⚠️ <i>{notice}</i>")

    markup = inline_keyboard(
        [
            callback_button("👥 Пользователи", "admin:users:0"),
            callback_button("📊 Статистика", "admin:stats"),
        ],
        [
            callback_button("⚙️ Настройки", "admin:settings"),
            callback_button("📢 Рассылка", "admin:broadcast:menu"),
        ],
        [
            callback_button("🧾 Аномалии оплат", "admin:payment_anomalies"),
            callback_button("🔄 Обновить invite", "admin:refresh_invite"),
        ],
        [
            callback_button("🏠 Главное меню", "panel:main"),
        ],
    )
    return "\n".join(text), markup


def get_admin_settings(settings, system, notice=None):
    text = [
        "<b>⚙️ Настройки системы</b>",
        f"Цена: <b>{settings['subscriptionPriceStars']} ⭐</b>",
        f"Срок: <b>{settings['subscriptionDurationDays']} дн.</b> | 🔔: <b>{settings['warningDays']} дн.</b>",
        f"Авто-ссылка: <b>{'Вкл' if system.get('autoCreateInviteLink') else 'Выкл'}</b>",
        "",
        f"Поддержка: @{settings.get('supportUsername') or '—'}",
    ]
    if notice:
        text.append(f"\n💡 <i>{notice}</i>")

    markup = inline_keyboard(
        [
            callback_button("💰 Цена", "admin:input:price"),
            callback_button("⏳ Срок", "admin:input:days"),
            callback_button("🔔 Варн", "admin:input:warning"),
        ],
        [
            callback_button("🔄 Recurring", "admin:toggle:recurring"),
            callback_button("🔗 Авто-invite", "admin:toggle:autoinvite"),
        ],
        [
            callback_button("📡 Канал", "admin:input:channel"),
            callback_button("🆘 Поддержка", "admin:input:support"),
        ],
        [
            callback_button("📝 Редактировать тексты", "admin:templates:menu"),
        ],
        [
            callback_button("🔙 Назад", "admin:menu"),
        ],
    )
    return "\n".join(text), markup


def get_admin_users(users, page, total_pages, current_filter="all", notice=None):
    filter_icons = {
        "all": "👥",
        "active": "✅",
        "expired": "❌",
        "non_buyers": "💎",
    }
    text = [
        f"<b>{filter_icons.get(current_filter, '👥')} Пользователи ({page + 1}/{total_pages})</b>",
    ]
    if notice:
        text.append(f"💡 <i>{notice}</i>")

    buttons = []
    buttons.append(
        [
            callback_button("Все" if current_filter != "all" else "🔘 Все", "admin:filter:all"),
            callback_button("✅ Активные", "admin:filter:active"),
            callback_button("❌ Истекшие", "admin:filter:expired"),
        ]
    )

    for user in users:
        name = format_user_name(user)
        sub_icon = "✅" if (user.get("subscriptionUntil") or 0) > time.time() * 1000 else "❌"
        buttons.append([callback_button(f"{sub_icon} {name} (ID: {user['id']})", f"admin:user:{user['id']}")])

    nav = []
    if page > 0:
        nav.append(callback_button("⬅️", f"admin:users:{page - 1}"))

    nav.append(callback_button("🔍 Поиск", "admin:input:search_user"))

    if page < total_pages - 1:
        nav.append(callback_button("➡️", f"admin:users:{page + 1}"))

    buttons.append(nav)
    buttons.append([callback_button("🔙 Назад", "admin:menu")])

    return "\n".join(text), {"inline_keyboard": buttons}


def get_admin_user_details(user, system, notice=None):
    sub_until = format_datetime(user.get("subscriptionUntil"), system["appTimezone"])
    text = [
        f"<b>👤 Пользователь {format_user_name(user)}</b>",
        f"ID: <code>{user['id']}</code>",
        f"Баланс: <b>{user.get('balanceStars', 0)} Stars</b>",
        f"Подписка до: <b>{sub_until}</b>",
        f"Статус в канале: <b>{user.get('channelMemberStatus') or 'неизвестно'}</b>",
        f"Заметка: <i>{user.get('notes') or '—'}</i>",
    ]
    if notice:
        text.append(f"\n⚠️ <i>{notice}</i>")

    markup = inline_keyboard(
        [
            callback_button("➕ Выдать дни", f"admin:input:grant:{user['id']}"),
            callback_button("💰 Изм. баланс", f"admin:input:balance:{user['id']}"),
        ],
        [
            callback_button("✅ Одобрить", f"admin:approve:{user['id']}"),
            callback_button("🚫 Снять доступ", f"admin:revoke:{user['id']}"),
        ],
        [
            callback_button("📝 Заметка", f"admin:input:note:{user['id']}"),
            callback_button("✉️ Сообщение", f"admin:input:msg:{user['id']}"),
        ],
        [
            callback_button("🔙 К списку", "admin:users:0"),
        ],
    )
    return "\n".join(text), markup


def get_admin_payment_diagnostics(user, diagnostics, system, notice=None):
    sub_until = format_datetime(diagnostics.get("subscriptionUntil"), system["appTimezone"])
    last_payment_at = format_datetime(diagnostics.get("lastPaymentAt"), system["appTimezone"])
    lines = [
        f"<b>🧾 Диагностика платежей: {format_user_name(user)}</b>",
        f"ID: <code>{diagnostics['userId']}</code>",
        f"Платежей в user stats: <b>{diagnostics['totalPaymentsCount']}</b>",
        f"Платежей в records: <b>{diagnostics['paymentCountByRecords']}</b>",
        f"Потрачено в user stats: <b>{diagnostics['totalSpentStars']} ⭐</b>",
        f"Сумма по records: <b>{diagnostics['paymentAmountByRecords']} ⭐</b>",
        f"Подписка активна: <b>{'Да' if diagnostics['subscriptionActive'] else 'Нет'}</b>",
        f"Подписка до: <b>{sub_until}</b>",
        f"Последний платеж: <b>{last_payment_at}</b>",
        "",
        "<b>⚠️ Recovery policy</b>",
        "Автоматическое восстановление отключено.",
        "Проверьте платёж вручную перед выдачей доступа.",
        "Ручное восстановление не меняет статистику оплат и не создаёт fake payment records.",
    ]

    warnings = diagnostics.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("<b>Подозрительные признаки</b>")
        for warning in warnings:
            lines.append(f"• {warning}")

    recent_payments = diagnostics.get("recentPayments") or []
    if recent_payments:
        lines.append("")
        lines.append("<b>Последние платежи</b>")
        for payment in recent_payments:
            paid_at = format_datetime(payment.get("paidAt"), system["appTimezone"])
            charge_id = payment.get("telegramPaymentChargeId") or "—"
            amount = payment.get("totalAmount", 0)
            lines.append(f"• {paid_at} | {amount} ⭐ | <code>{charge_id}</code>")

    lines.append("")
    lines.append(
        f"Если платёж подтверждён вручную, используйте:\n"
        f"<code>/admin_recover_payment {diagnostics['userId']} 30 manual_verification</code>"
    )

    if notice:
        lines.append(f"\n💡 <i>{notice}</i>")

    markup = inline_keyboard(
        [callback_button("👤 К пользователю", f"admin:user:{diagnostics['userId']}")],
        [callback_button("🔙 Назад", "admin:menu")],
    )
    return "\n".join(lines), markup


def get_admin_payment_anomalies(anomalies, limit, notice=None):
    lines = [
        "<b>🧾 Подозрительные payment-cases</b>",
        f"Показано до <b>{limit}</b> пользователей.",
        "Список только для диагностики. Автоматическое восстановление отключено.",
    ]
    if notice:
        lines.append(f"\n💡 <i>{notice}</i>")

    if not anomalies:
        lines.extend([
            "",
            "Подозрительных payment-cases не найдено.",
        ])
    else:
        for item in anomalies:
            summary = "; ".join((item.get("warnings") or [])[:2]) or "Есть предупреждения."
            lines.extend([
                "",
                f"<b>{item['displayName']}</b> | ID <code>{item['userId']}</code>",
                f"Платежей: <b>{item['totalPaymentsCount']}</b> | Потрачено: <b>{item['totalSpentStars']} ⭐</b>",
                f"Подписка активна: <b>{'Да' if item['subscriptionActive'] else 'Нет'}</b>",
                f"Причины: {summary}",
                f"Команда: <code>/admin_payment_diag {item['userId']}</code>",
            ])

    markup = inline_keyboard([callback_button("🔙 Назад", "admin:menu")])
    return "\n".join(lines), markup


def get_admin_templates_menu(templates):
    text = [
        "<b>📝 Редактор текстов</b>",
        "Выберите шаблон для изменения:",
    ]
    buttons = []
    labels = {
        "welcomeText": "👋 Приветствие",
        "subscriptionName": "🏷 Название подписки",
        "subscriptionDescription": "📝 Описание в счете",
        "paymentReceived": "✅ После оплаты",
        "subscriptionExpired": "❌ При истечении",
        "joinInstructions": "🔗 Инструкция входа",
        "noSubscription": "⚠️ Нет подписки",
        "support": "🆘 Текст поддержки",
    }
    for key, label in labels.items():
        buttons.append([callback_button(label, f"admin:templates:edit:{key}")])

    buttons.append([callback_button("🔙 Назад", "admin:settings")])
    return "\n".join(text), {"inline_keyboard": buttons}


def get_admin_template_editor(key, current_val):
    text = [
        f"<b>📝 Редактирование: {key}</b>",
        "",
        "Текущий текст:",
        f"<i>{current_val or '—'}</i>",
        "",
        "Введите новый текст в ответном сообщении или нажмите «Отмена».",
    ]
    return "\n".join(text), inline_keyboard([callback_button("❌ Отмена", "admin:templates:menu")])


def get_admin_broadcast_menu():
    text = [
        "<b>📢 Рассылка сообщений</b>",
        "Выберите аудиторию:",
    ]
    markup = inline_keyboard(
        [callback_button("Всем пользователям", "admin:input:broadcast:all")],
        [callback_button("Только активным", "admin:input:broadcast:active")],
        [callback_button("Только истекшим", "admin:input:broadcast:expired")],
        [callback_button("🔙 Назад", "admin:menu")],
    )
    return "\n".join(text), markup

import time
from math import ceil

from utils_py import format_datetime


DAY_MS = 24 * 60 * 60 * 1000


def _pluralize_days(days):
    remainder_100 = days % 100
    remainder_10 = days % 10
    if 11 <= remainder_100 <= 14:
        return "дней"
    if remainder_10 == 1:
        return "день"
    if 2 <= remainder_10 <= 4:
        return "дня"
    return "дней"


def format_days_left(subscription_until, now_ms=None):
    if not subscription_until:
        return None

    if now_ms is None:
        now_ms = int(time.time() * 1000)

    remaining_ms = int(subscription_until) - int(now_ms)
    if remaining_ms <= 0:
        return None

    if remaining_ms < DAY_MS:
        return "меньше суток"

    days = max(1, ceil(remaining_ms / DAY_MS))
    return f"{days} {_pluralize_days(days)}"


def build_main_menu_status_lines(context, now_ms=None):
    user = context.get("user") or {}
    system = context.get("system") or {}
    time_zone = system.get("appTimezone") or "UTC"
    is_active = bool(context.get("is_active"))
    has_pending_join = bool(user.get("pendingJoinRequest"))
    effective_invite_link = context.get("effective_invite_link") or ""
    subscription_until = user.get("subscriptionUntil")

    if is_active:
        lines = [
            f"Статус: <b>активна</b> до <b>{format_datetime(subscription_until, time_zone)}</b>.",
        ]
        days_left = format_days_left(subscription_until, now_ms=now_ms)
        if days_left:
            lines.append(f"Осталось: <b>{days_left}</b>.")

        if has_pending_join:
            lines.append("Заявка в канал уже отправлена. Бот одобрит её автоматически.")
        elif effective_invite_link:
            lines.append("Если вы ещё не в канале, нажмите «Открыть канал» ниже и отправьте заявку.")
        else:
            lines.append("Если кнопка входа ещё не появилась, нажмите «Получить ссылку» ниже.")
        return lines

    if has_pending_join:
        return [
            "Статус: <b>не активна</b>.",
            "Заявка в канал уже отправлена. Оплатите доступ, и бот одобрит её автоматически.",
        ]

    return [
        "Статус: <b>не активна</b>.",
        "После оплаты используйте кнопку «Получить ссылку», чтобы войти в канал.",
    ]


def build_help_text(support_username):
    text = [
        "<b>📖 Справка по боту</b>",
        "",
        "1. <b>Как купить доступ?</b> Нажмите кнопку «Купить доступ» и оплатите счёт через Telegram Stars.",
        "2. <b>Что делать после оплаты?</b> Вернитесь в главное меню. Если ссылка уже доступна, используйте кнопку «Открыть канал». Если нет, нажмите «Получить ссылку».",
        "3. <b>Если заявка уже отправлена?</b> Бот одобрит её автоматически, как только доступ станет активным.",
        "4. <b>Если что-то не работает?</b> Проверьте статус подписки в главном меню и напишите в поддержку.",
    ]

    if support_username:
        text.extend(["", f"По всем вопросам: @{support_username.lstrip('@')}"])

    return "\n".join(text)


def build_invoice_sent_notice():
    return "Счёт на оплату отправлен отдельным сообщением. После оплаты вернитесь в меню и откройте канал по кнопке ниже."


def build_balance_purchase_notice(user, time_zone):
    return (
        "✅ Подписка успешно оплачена с баланса и активна до "
        f"<b>{format_datetime((user or {}).get('subscriptionUntil'), time_zone)}</b>. "
        "Если вы ещё не в канале, используйте кнопку ниже."
    )

import time

from bot.ui import UIProvider
from utils_py import format_user_name, parse_integer


def render_main(handler, user_id, notice=None, force_new=False):
    stats = handler.bot.get_dashboard_stats_extended()
    system = handler.bot.get_effective_system_settings()
    invite_link = handler.store.get_effective_invite_link(handler.bot.config.channel_invite_link)
    text, markup = handler.ui.get_admin_main(stats, system, invite_link, notice)
    handler.bot.render_panel(user_id, text, markup, "admin:menu", force_new=force_new)


def render_settings(handler, user_id, notice=None):
    settings = handler.store.get_settings()
    system = handler.bot.get_effective_system_settings()
    text, markup = handler.ui.get_admin_settings(settings, system, notice)
    handler.bot.render_panel(user_id, text, markup, "admin:settings")


def render_templates_menu(handler, user_id, notice=None):
    settings = handler.store.get_settings()
    text, markup = handler.ui.get_admin_templates_menu(settings)
    if notice:
        text = f"💡 <i>{notice}</i>\n\n" + text
    handler.bot.render_panel(user_id, text, markup, "admin:templates:menu")


def render_users(handler, user_id, page, notice=None):
    all_users = handler.store.list_users()
    filter_val = handler.fsm.get_data(user_id, "user_filter") or "all"
    query = handler.fsm.get_data(user_id, "user_search_query")
    now = time.time() * 1000

    if query:
        q = query.lower()
        all_users = [
            user for user in all_users
            if q in str(user["id"])
            or q in (user.get("username") or "").lower()
            or q in format_user_name(user).lower()
        ]

    if filter_val == "active":
        all_users = [user for user in all_users if (user.get("subscriptionUntil") or 0) > now]
    elif filter_val == "expired":
        all_users = [user for user in all_users if (user.get("subscriptionUntil") or 0) <= now]
    elif filter_val == "non_buyers":
        all_users = [user for user in all_users if not user.get("totalPaymentsCount")]

    page_size = 8
    total_pages = max(1, (len(all_users) + page_size - 1) // page_size)
    page = min(page, total_pages - 1)
    users_slice = all_users[page * page_size:(page + 1) * page_size]

    text, markup = handler.ui.get_admin_users(users_slice, page, total_pages, filter_val, notice)
    handler.bot.render_panel(user_id, text, markup, f"admin:users:{page}")


def render_user_details(handler, user_id, target_id, notice=None):
    user = handler.store.get_user(target_id)
    if not user:
        render_users(handler, user_id, 0, notice="Пользователь не найден")
        return

    system = handler.bot.get_effective_system_settings()
    text, markup = handler.ui.get_admin_user_details(user, system, notice)
    handler.bot.render_panel(user_id, text, markup, f"admin:user:{target_id}")


def render_stats(handler, user_id):
    stats = handler.bot.get_dashboard_stats_extended()
    text = [
        "<b>📊 Расширенная статистика</b>",
        f"Всего юзеров: <b>{stats['totalUsers']}</b>",
        f"Активных подписок: <b>{stats['activeSubscriptions']}</b>",
        f"Истекших: <b>{stats['expiredSubscriptions']}</b>",
        "",
        f"Доход (всего): <b>{stats['revenueStars']} ⭐</b>",
        f"Доход (30 дней): <b>{stats.get('revenueMonth', 0)} ⭐</b>",
        "",
        f"В канале: <b>{stats['channelMembers']}</b>",
        f"Ожидают: <b>{stats['pendingJoinRequests']}</b>",
    ]
    markup = {"inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "admin:menu"}]]}
    handler.bot.render_panel(user_id, "\n".join(text), markup, "admin:stats")


def render_payment_diagnostics(handler, user_id, target_id, notice=None):
    target_id = parse_integer(target_id)
    diagnostics = handler.store.get_user_payment_diagnostics(target_id)
    if not diagnostics:
        render_main(handler, user_id, notice="Пользователь для диагностики не найден")
        return

    user = handler.store.get_user(target_id)
    system = handler.bot.get_effective_system_settings()
    text, markup = handler.ui.get_admin_payment_diagnostics(user, diagnostics, system, notice)
    handler.bot.render_panel(user_id, text, markup, f"admin:payment_diag:{target_id}")


def render_payment_anomalies(handler, user_id, limit=20, notice=None):
    anomalies = handler.store.list_payment_anomalies(limit=limit)
    text, markup = handler.ui.get_admin_payment_anomalies(anomalies, limit, notice)
    handler.bot.render_panel(user_id, text, markup, "admin:payment_anomalies")


def render_input_request(handler, user_id, text):
    markup = {"inline_keyboard": [[{"text": "❌ Отмена", "callback_data": "admin:menu"}]]}
    handler.bot.render_panel(user_id, text, markup, "admin:input_request")

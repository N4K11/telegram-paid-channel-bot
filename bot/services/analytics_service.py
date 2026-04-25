from datetime import datetime, timedelta, timezone

from utils_py import format_datetime, format_user_name, resolve_timezone


def _ensure_now_ms(now_ms):
    if now_ms is not None:
        return int(now_ms)
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def _utc_ms(local_dt):
    return int(local_dt.astimezone(timezone.utc).timestamp() * 1000)


def _period_starts(now_ms, time_zone):
    zone = resolve_timezone(time_zone)
    local_now = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).astimezone(zone)
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=day_start.weekday())
    month_start = day_start.replace(day=1)
    return {
        "localNow": local_now,
        "dayStartMs": _utc_ms(day_start),
        "weekStartMs": _utc_ms(week_start),
        "monthStartMs": _utc_ms(month_start),
    }


def _collect_top_users(users, limit=5):
    ranked = sorted(
        users,
        key=lambda user: (
            -(user.get("totalSpentStars") or 0),
            -(user.get("totalPaymentsCount") or 0),
            user.get("id") or 0,
        ),
    )
    top_users = []
    for user in ranked[:limit]:
        if not (user.get("totalSpentStars") or user.get("totalPaymentsCount")):
            continue
        top_users.append(
            {
                "userId": user["id"],
                "displayName": format_user_name(user),
                "totalSpentStars": user.get("totalSpentStars") or 0,
                "totalPaymentsCount": user.get("totalPaymentsCount") or 0,
                "lastPaymentAt": user.get("lastPaymentAt"),
            }
        )
    return top_users


def get_analytics_snapshot(app, now_ms=None):
    current_time_ms = _ensure_now_ms(now_ms)
    system = app.get_effective_system_settings()
    time_zone = system["appTimezone"]
    periods = _period_starts(current_time_ms, time_zone)
    users = app.store.list_users()
    payments = app.store.get_payments()
    stats = app.store.get_dashboard_stats(current_time_ms=current_time_ms)

    revenue_day = 0
    revenue_week = 0
    revenue_month = 0
    payers_day = set()
    payers_week = set()
    payers_month = set()

    for payment in payments:
        paid_at = payment.get("paidAt") or 0
        amount = payment.get("totalAmount") or 0
        user_id = payment.get("userId")
        if paid_at >= periods["monthStartMs"]:
            revenue_month += amount
            payers_month.add(user_id)
        if paid_at >= periods["weekStartMs"]:
            revenue_week += amount
            payers_week.add(user_id)
        if paid_at >= periods["dayStartMs"]:
            revenue_day += amount
            payers_day.add(user_id)

    return {
        "timeZone": time_zone,
        "generatedAt": current_time_ms,
        "stats": stats,
        "revenueTotal": stats.get("revenueStars", 0),
        "revenueDay": revenue_day,
        "revenueWeek": revenue_week,
        "revenueMonth": revenue_month,
        "payersDay": len(payers_day),
        "payersWeek": len(payers_week),
        "payersMonth": len(payers_month),
        "topUsers": _collect_top_users(users),
        "lastPaymentAt": payments[0].get("paidAt") if payments else None,
        "periodStarts": periods,
    }


def format_stats_summary(snapshot):
    stats = snapshot["stats"]
    lines = [
        "<b>📊 Расширенная статистика</b>",
        f"Всего юзеров: <b>{stats['totalUsers']}</b>",
        f"Активных подписок: <b>{stats['activeSubscriptions']}</b>",
        f"Истекших: <b>{stats['expiredSubscriptions']}</b>",
        f"Скоро истекают: <b>{stats['expiringSoon']}</b>",
        f"Ожидают вход: <b>{stats['pendingJoinRequests']}</b>",
        "",
        f"Доход всего: <b>{snapshot['revenueTotal']} ⭐</b>",
        f"Доход за день: <b>{snapshot['revenueDay']} ⭐</b>",
        f"Доход за неделю: <b>{snapshot['revenueWeek']} ⭐</b>",
        f"Доход за 30 дней: <b>{snapshot['revenueMonth']} ⭐</b>",
    ]
    top_users = snapshot.get("topUsers") or []
    if top_users:
        lines.extend(
            [
                "",
                "<b>Топ по оплатам</b>",
                *[
                    f"• {item['displayName']} — <b>{item['totalSpentStars']} ⭐</b> ({item['totalPaymentsCount']} оплат)"
                    for item in top_users[:3]
                ],
            ]
        )
    return "\n".join(lines)


def format_revenue_report(snapshot):
    lines = [
        "<b>💰 Доход и платежи</b>",
        f"Всего заработано: <b>{snapshot['revenueTotal']} ⭐</b>",
        f"За день: <b>{snapshot['revenueDay']} ⭐</b>",
        f"За неделю: <b>{snapshot['revenueWeek']} ⭐</b>",
        f"За 30 дней: <b>{snapshot['revenueMonth']} ⭐</b>",
        "",
        f"Плательщиков за день: <b>{snapshot['payersDay']}</b>",
        f"Плательщиков за неделю: <b>{snapshot['payersWeek']}</b>",
        f"Плательщиков за 30 дней: <b>{snapshot['payersMonth']}</b>",
    ]
    top_users = snapshot.get("topUsers") or []
    if top_users:
        lines.extend(
            [
                "",
                "<b>Топ пользователей по оплатам</b>",
                *[
                    f"• {item['displayName']} — <b>{item['totalSpentStars']} ⭐</b> ({item['totalPaymentsCount']} оплат)"
                    for item in top_users
                ],
            ]
        )
    return "\n".join(lines)


def format_activity_report(snapshot):
    stats = snapshot["stats"]
    lines = [
        "<b>👥 Активность пользователей</b>",
        f"Всего юзеров: <b>{stats['totalUsers']}</b>",
        f"Активных подписок: <b>{stats['activeSubscriptions']}</b>",
        f"Истекших: <b>{stats['expiredSubscriptions']}</b>",
        f"Скоро истекают: <b>{stats['expiringSoon']}</b>",
        f"Ожидают вход: <b>{stats['pendingJoinRequests']}</b>",
        f"В канале: <b>{stats['channelMembers']}</b>",
        "",
        f"Последний платёж: <b>{format_datetime(snapshot.get('lastPaymentAt'), snapshot['timeZone'])}</b>",
        f"Плательщиков за день: <b>{snapshot['payersDay']}</b>",
        f"Плательщиков за неделю: <b>{snapshot['payersWeek']}</b>",
        f"Плательщиков за 30 дней: <b>{snapshot['payersMonth']}</b>",
    ]
    top_users = snapshot.get("topUsers") or []
    if top_users:
        lines.extend(
            [
                "",
                "<b>Самые активные по оплатам</b>",
                *[
                    f"• {item['displayName']} — {item['totalPaymentsCount']} оплат, {item['totalSpentStars']} ⭐"
                    for item in top_users
                ],
            ]
        )
    return "\n".join(lines)

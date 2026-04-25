import json
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit

from utils_py import (
    create_signature,
    escape_html,
    format_datetime,
    format_relative_duration,
    format_user_name,
    parse_boolean_from_form,
    parse_cookies,
    parse_form_encoded,
    parse_integer,
    to_json_bytes,
)


def selected(current_value, expected_value):
    return "selected" if current_value == expected_value else ""


def checked(value):
    return "checked" if value else ""


def escape_csv(value):
    normalized = str(value if value is not None else "").replace('"', '""')
    return f'"{normalized}"'


def build_users_csv(users, time_zone):
    header = ",".join([
        "id",
        "username",
        "name",
        "balanceStars",
        "subscriptionUntil",
        "channelMemberStatus",
        "pendingJoinRequest",
        "totalSpentStars",
        "totalPaymentsCount",
        "notes"
    ])
    rows = [header]
    for user in users:
        rows.append(",".join([
            escape_csv(user.get("id", "")),
            escape_csv(user.get("username", "")),
            escape_csv(format_user_name(user)),
            escape_csv(user.get("balanceStars", 0)),
            escape_csv(format_datetime(user.get("subscriptionUntil"), time_zone) if user.get("subscriptionUntil") else ""),
            escape_csv(user.get("channelMemberStatus", "")),
            escape_csv("yes" if user.get("pendingJoinRequest") else "no"),
            escape_csv(user.get("totalSpentStars", 0)),
            escape_csv(user.get("totalPaymentsCount", 0)),
            escape_csv(user.get("notes", "")),
        ]))
    return "\n".join(rows)


def text_area(name, value, rows=10):
    return f'<textarea name="{escape_html(name)}" rows="{rows}">{escape_html(value or "")}</textarea>'


def parse_redirect_back(query):
    back = query.get("back", ["/"])[0]
    return back if back.startswith("/") else "/"


def parse_system_settings(form):
    return {
        "botTokenOverride": form.get("botTokenOverride", ""),
        "channelId": form.get("channelId", ""),
        "appTimezone": form.get("appTimezone", ""),
        "adminUsername": form.get("adminUsername", ""),
        "adminPassword": form.get("adminPassword", ""),
        "pollTimeoutSeconds": max(1, parse_integer(form.get("pollTimeoutSeconds"), 25)),
        "serviceCheckIntervalMs": max(10_000, parse_integer(form.get("serviceCheckIntervalMs"), 60_000)),
        "autoCreateInviteLink": parse_boolean_from_form(form.get("autoCreateInviteLink"))
    }


def render_layout(title, content):
    return (
        "<!DOCTYPE html><html lang=\"ru\"><head><meta charset=\"utf-8\" />"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />"
        f"<title>{escape_html(title)}</title>"
        "<style>"
        "body{margin:0;font-family:Segoe UI,Tahoma,sans-serif;background:#f4efe5;color:#16212b;}"
        ".shell{max-width:1400px;margin:20px auto;padding:0 14px;}"
        ".card,.hero{background:#fffdf8;border:1px solid #d8ccb8;border-radius:20px;box-shadow:0 8px 24px rgba(0,0,0,.06);padding:18px;}"
        ".hero{margin-bottom:16px;}"
        ".grid{display:grid;grid-template-columns:380px 1fr;gap:16px;}"
        ".split{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px;}"
        ".stack{display:grid;gap:16px;}"
        ".cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:16px 0;}"
        ".metric{padding:14px;border:1px solid #e1d7c7;border-radius:16px;background:#fff;}"
        ".muted{color:#6a7480;}"
        ".row,.toolbar{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap;}"
        "form{display:grid;gap:10px;}"
        "label{display:grid;gap:6px;font-size:13px;color:#52606d;}"
        "input,textarea,select,button{font:inherit;}"
        "input,textarea,select{width:100%;padding:10px 12px;border-radius:12px;border:1px solid #cdbfa8;background:#fff;}"
        "textarea{resize:vertical;min-height:90px;}"
        "button{padding:10px 14px;border:0;border-radius:12px;background:#0f766e;color:#fff;font-weight:700;cursor:pointer;}"
        "button.secondary{background:#27415c;}button.ghost{background:#fff;color:#16212b;border:1px solid #d8ccb8;}button.danger{background:#b42318;}"
        ".flash{margin:0 0 14px;padding:12px 14px;border-radius:14px;background:#e6f7f3;border:1px solid #b8e2d8;color:#0d5e55;}"
        ".pill{display:inline-block;padding:4px 10px;border-radius:999px;background:#d7efe9;color:#0f766e;font-size:12px;font-weight:700;}"
        ".pill.danger{background:#fee7e5;color:#b42318;}.pill.waiting{background:#fff0d2;color:#9a5c00;}"
        ".table-wrap{overflow:auto;}table{width:100%;border-collapse:collapse;}th,td{padding:10px;border-bottom:1px solid #e7dccb;text-align:left;vertical-align:top;}"
        "th{font-size:12px;text-transform:uppercase;color:#6a7480;}"
        ".compact{display:grid;grid-template-columns:120px 1fr auto;gap:8px;align-items:end;}"
        ".compact-two{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:end;}"
        ".actions{display:grid;gap:8px;min-width:260px;}"
        "a{color:#0f766e;text-decoration:none;}"
        "@media(max-width:1100px){.grid,.split{grid-template-columns:1fr;}.compact,.compact-two{grid-template-columns:1fr;}}"
        "</style></head><body>"
        f"{content}</body></html>"
    )


def render_login(error_text=""):
    flash = (
        f'<div class="flash" style="background:#fee7e5;border-color:#f4c7c3;color:#8f1d14">{escape_html(error_text)}</div>'
        if error_text else ""
    )
    return render_layout("Вход в админку", (
        '<main class="shell" style="max-width:460px;margin-top:70px">'
        '<section class="card">'
        '<div class="row"><div><h1>Админ-панель</h1>'
        '<p class="muted">Управление подписчиками, оплатами и доступом к каналу.</p></div></div>'
        f"{flash}"
        '<form method="post" action="/login">'
        '<label>Логин<input type="text" name="username" autocomplete="username" required /></label>'
        '<label>Пароль<input type="password" name="password" autocomplete="current-password" required /></label>'
        '<button type="submit">Войти</button>'
        '</form></section></main>'
    ))


def render_user_status(user, time_zone):
    if user.get("pendingJoinRequest"):
        created_at = user["pendingJoinRequest"].get("createdAt")
        return (
            '<span class="pill waiting">Есть заявка</span><br />'
            f'<span class="muted">{escape_html(format_datetime(created_at, time_zone))}</span>'
        )

    if user.get("subscriptionUntil") and user["subscriptionUntil"] > int(__import__("time").time() * 1000):
        return (
            '<span class="pill">Активна</span><br />'
            f'<span class="muted">{escape_html(format_datetime(user["subscriptionUntil"], time_zone))}</span><br />'
            f'<span class="muted">{escape_html(format_relative_duration(user["subscriptionUntil"]))}</span>'
        )

    if user.get("subscriptionUntil"):
        return (
            '<span class="pill danger">Истекла</span><br />'
            f'<span class="muted">{escape_html(format_datetime(user["subscriptionUntil"], time_zone))}</span>'
        )

    return '<span class="pill danger">Нет подписки</span>'


def render_dashboard(view_model):
    stats = view_model["stats"]
    settings = view_model["settings"]
    system = view_model["system"]
    users = view_model["users"]
    payments = view_model["payments"]
    audit_log = view_model["auditLog"]
    flash_message = view_model.get("flashMessage") or ""
    time_zone = view_model["timeZone"]
    filters = view_model["filters"]
    state_json = view_model["stateJson"]
    settings_json = view_model["settingsJson"]
    templates_json = view_model["templatesJson"]

    user_rows = []
    for user in users:
        username = f"@{escape_html(user['username'])}" if user.get("username") else "—"
        user_rows.append(
            "<tr>"
            "<td>"
            f"<strong>{escape_html(format_user_name(user))}</strong><br />"
            f"<span class=\"muted\">{username}</span><br />"
            f"<span class=\"muted\">ID {user['id']}</span>"
            "</td>"
            f"<td>{render_user_status(user, time_zone)}</td>"
            "<td>"
            f"<strong>{user.get('balanceStars', 0)} Stars</strong><br />"
            f"<span class=\"muted\">В канале: {escape_html(user.get('channelMemberStatus') or 'unknown')}</span><br />"
            f"<span class=\"muted\">Платежей: {user.get('totalPaymentsCount', 0)}</span><br />"
            f"<span class=\"muted\">Потрачено: {user.get('totalSpentStars', 0)} Stars</span>"
            "</td>"
            "<td class=\"actions\">"
            f"<a href=\"/users/{user['id']}\"><button class=\"ghost\" type=\"button\">Полный редактор</button></a>"
            f"<form method=\"post\" action=\"/users/{user['id']}/subscription\">"
            f"<div class=\"compact\"><label>Дней<input type=\"number\" name=\"days\" min=\"1\" value=\"{settings['subscriptionDurationDays']}\" /></label>"
            "<label>Причина<input type=\"text\" name=\"reason\" value=\"admin_grant\" /></label>"
            "<button type=\"submit\">Выдать</button></div></form>"
            f"<form method=\"post\" action=\"/users/{user['id']}/balance\">"
            "<div class=\"compact\"><label>Баланс<input type=\"number\" name=\"amount\" value=\"50\" /></label>"
            "<label>Причина<input type=\"text\" name=\"reason\" value=\"admin_balance\" /></label>"
            "<button class=\"secondary\" type=\"submit\">Изменить</button></div></form>"
            f"<form method=\"post\" action=\"/users/{user['id']}/message\">"
            "<div class=\"compact-two\"><label>Сообщение<input type=\"text\" name=\"text\" placeholder=\"Написать пользователю...\" required /></label>"
            "<button class=\"secondary\" type=\"submit\">Отправить</button></div></form>"
            f"<form method=\"post\" action=\"/users/{user['id']}/notes\">"
            f"<label>Заметка<textarea name=\"notes\" rows=\"4\">{escape_html(user.get('notes') or '')}</textarea></label>"
            "<button class=\"ghost\" type=\"submit\">Сохранить заметку</button></form>"
            "<div class=\"row\">"
            f"<form method=\"post\" action=\"/users/{user['id']}/approve\"><button class=\"secondary\" type=\"submit\">Одобрить заявку</button></form>"
            f"<form method=\"post\" action=\"/users/{user['id']}/revoke\"><button class=\"danger\" type=\"submit\">Снять доступ</button></form>"
            "</div>"
            "</td>"
            "</tr>"
        )

    payment_rows = []
    for payment in payments:
        payment_rows.append(
            "<tr>"
            f"<td>{escape_html(payment.get('invoicePayload', ''))}</td>"
            f"<td>ID {payment.get('userId', '')}</td>"
            f"<td>{payment.get('totalAmount', 0)} Stars</td>"
            f"<td>{escape_html(format_datetime(payment.get('paidAt'), time_zone))}</td>"
            "</tr>"
        )

    audit_rows = []
    for item in audit_log:
        audit_rows.append(
            "<tr>"
            f"<td>{escape_html(item.get('type', ''))}</td>"
            f"<td>{'ID ' + str(item['userId']) if item.get('userId') else '—'}</td>"
            f"<td>{escape_html(json.dumps(item, ensure_ascii=False))}</td>"
            f"<td>{escape_html(item.get('createdAt', ''))}</td>"
            "</tr>"
        )

    flash_html = f'<div class="flash">{escape_html(flash_message)}</div>' if flash_message else ""
    user_rows_html = "".join(user_rows) or '<tr><td colspan="4" class="muted">По текущему фильтру пользователей нет.</td></tr>'
    payment_rows_html = "".join(payment_rows) or '<tr><td colspan="4" class="muted">Платежей пока нет.</td></tr>'
    audit_rows_html = "".join(audit_rows) or '<tr><td colspan="4" class="muted">Аудит пока пуст.</td></tr>'

    return render_layout("Админ-панель", (
        '<main class="shell">'
        '<section class="hero">'
        '<div class="row"><div><h1>Управление платным каналом</h1>'
        '<p class="muted">Поиск по подписчикам, ручные действия, рассылка, экспорт и настройки в одном месте.</p>'
        '</div><form method="post" action="/logout"><button class="secondary" type="submit">Выйти</button></form></div>'
        '<form class="row" method="get" action="/">'
        f'<label style="flex:1">Поиск<input type="text" name="q" value="{escape_html(filters["q"])}" placeholder="ID, username, имя, заметка" /></label>'
        '<label>Фильтр<select name="status">'
        f'<option value="all" {selected(filters["status"], "all")}>Все</option>'
        f'<option value="active" {selected(filters["status"], "active")}>Активные</option>'
        f'<option value="soon" {selected(filters["status"], "soon")}>Истекают скоро</option>'
        f'<option value="pending" {selected(filters["status"], "pending")}>С заявкой</option>'
        f'<option value="expired" {selected(filters["status"], "expired")}>Истекшие</option>'
        f'<option value="inactive" {selected(filters["status"], "inactive")}>Без подписки</option>'
        '</select></label>'
        '<button type="submit">Применить</button><a href="/"><button class="ghost" type="button">Сбросить</button></a>'
        '</form></section>'
        f"{flash_html}"
        '<section class="cards">'
        f'<article class="metric"><span class="muted">Всего пользователей</span><strong>{stats["totalUsers"]}</strong></article>'
        f'<article class="metric"><span class="muted">Активные подписки</span><strong>{stats["activeSubscriptions"]}</strong></article>'
        f'<article class="metric"><span class="muted">Скоро истекают</span><strong>{stats["expiringSoon"]}</strong></article>'
        f'<article class="metric"><span class="muted">Ожидают одобрения</span><strong>{stats["pendingJoinRequests"]}</strong></article>'
        f'<article class="metric"><span class="muted">Доход</span><strong>{stats["revenueStars"]} Stars</strong></article>'
        f'<article class="metric"><span class="muted">Баланс пользователей</span><strong>{stats["totalBalanceStars"]} Stars</strong></article>'
        f'<article class="metric"><span class="muted">Участников в канале</span><strong>{stats["channelMembers"]}</strong></article>'
        f'<article class="metric"><span class="muted">Recurring</span><strong>{"ON" if stats["recurringEnabled"] else "OFF"}</strong></article>'
        '</section>'
        '<section class="grid"><div class="stack">'
        '<article class="card"><h2>Базовые настройки</h2>'
        '<form method="post" action="/settings">'
        f'<label>Цена подписки в Stars<input type="number" min="1" name="subscriptionPriceStars" value="{settings["subscriptionPriceStars"]}" required /></label>'
        f'<label>Длительность подписки в днях<input type="number" min="1" name="subscriptionDurationDays" value="{settings["subscriptionDurationDays"]}" required /></label>'
        f'<label>Предупреждать за сколько дней<input type="number" min="1" name="warningDays" value="{settings["warningDays"]}" required /></label>'
        f'<label>Название подписки<input type="text" name="subscriptionName" value="{escape_html(settings["subscriptionName"])}" required /></label>'
        f'<label>Описание<textarea name="subscriptionDescription" required>{escape_html(settings["subscriptionDescription"])}</textarea></label>'
        f'<label>Welcome-текст<textarea name="welcomeText">{escape_html(settings.get("welcomeText") or "")}</textarea></label>'
        f'<label>Support username<input type="text" name="supportUsername" value="{escape_html(settings.get("supportUsername") or "")}" /></label>'
        f'<label>Ссылка на канал<input type="text" name="channelInviteLink" value="{escape_html(settings.get("channelInviteLink") or "")}" /></label>'
        f'<label><input type="checkbox" name="recurringPaymentsEnabled" {checked(settings.get("recurringPaymentsEnabled"))} /> Включить recurring-платёж на 30 дней</label>'
        '<button type="submit">Сохранить настройки</button></form></article>'
        '<article class="card"><h2>Системные настройки</h2>'
        '<form method="post" action="/settings/system">'
        f'<label>Bot token override<input type="text" name="botTokenOverride" value="{escape_html(settings.get("botTokenOverride") or "")}" /></label>'
        f'<label>Channel ID override<input type="text" name="channelId" value="{escape_html(settings.get("channelId") or "")}" /></label>'
        f'<label>Timezone<input type="text" name="appTimezone" value="{escape_html(settings.get("appTimezone") or system["appTimezone"])}" /></label>'
        f'<label>Admin username<input type="text" name="adminUsername" value="{escape_html(settings.get("adminUsername") or system["adminUsername"])}" /></label>'
        f'<label>Admin password<input type="text" name="adminPassword" value="{escape_html(settings.get("adminPassword") or system["adminPassword"])}" /></label>'
        f'<label>Poll timeout seconds<input type="number" min="1" name="pollTimeoutSeconds" value="{escape_html(str(settings.get("pollTimeoutSeconds") or system["pollTimeoutSeconds"]))}" /></label>'
        f'<label>Service check interval ms<input type="number" min="10000" step="1000" name="serviceCheckIntervalMs" value="{escape_html(str(settings.get("serviceCheckIntervalMs") or system["serviceCheckIntervalMs"]))}" /></label>'
        f'<label><input type="checkbox" name="autoCreateInviteLink" {checked(system["autoCreateInviteLink"])} /> Автоматически создавать invite link</label>'
        '<button class="secondary" type="submit">Сохранить системные настройки</button></form></article>'
        '<article class="card"><h2>Служебные действия</h2>'
        '<form method="post" action="/actions/invite-link/refresh"><button class="secondary" type="submit">Пересоздать invite link</button></form>'
        '<form method="post" action="/users/create" style="margin-top:12px"><label>Новый user ID<input type="number" name="id" min="1" required /></label><button type="submit">Создать пустого пользователя</button></form>'
        f'<div style="margin-top:12px"><a href="/export/users.csv?q={quote(filters["q"])}&status={quote(filters["status"])}">Скачать CSV пользователей</a></div>'
        '</article>'
        '<article class="card"><h2>Массовая рассылка</h2>'
        '<form method="post" action="/broadcast"><label>Кому<select name="scope">'
        '<option value="all">Всем</option><option value="active">Только активным</option><option value="soon">Только скоро истекающим</option>'
        '<option value="pending">Только с заявкой</option><option value="expired">Только истекшим</option></select></label>'
        '<label>Текст<textarea name="text" required></textarea></label><button type="submit">Отправить рассылку</button></form></article>'
        '</div>'
        '<article class="card"><h2>Подписчики</h2><div class="table-wrap"><table><thead><tr><th>Пользователь</th><th>Статус</th><th>Сводка</th><th>Действия</th></tr></thead><tbody>'
        f'{user_rows_html}'
        '</tbody></table></div></article></section>'
        '<section class="split">'
        '<article class="card"><h2>JSON настроек</h2>'
        f'<form method="post" action="/json/settings"><label>Settings JSON{text_area("json", settings_json, 18)}</label><button type="submit">Сохранить settings JSON</button></form>'
        f'<form method="post" action="/json/templates" style="margin-top:12px"><label>Message templates JSON{text_area("json", templates_json, 14)}</label><button class="secondary" type="submit">Сохранить шаблоны</button></form>'
        '</article>'
        '<article class="card"><h2>Полная база JSON</h2>'
        f'<form method="post" action="/json/state"><label>State JSON{text_area("json", state_json, 24)}</label><button class="danger" type="submit">Заменить всё состояние</button></form>'
        '</article></section>'
        '<section class="split">'
        '<article class="card"><h2>Последние платежи</h2><div class="table-wrap"><table><thead><tr><th>Payload</th><th>Пользователь</th><th>Сумма</th><th>Дата</th></tr></thead><tbody>'
        f'{payment_rows_html}'
        '</tbody></table></div></article>'
        '<article class="card"><h2>Аудит</h2><div class="table-wrap"><table><thead><tr><th>Тип</th><th>Пользователь</th><th>Детали</th><th>Дата</th></tr></thead><tbody>'
        f'{audit_rows_html}'
        '</tbody></table></div></article></section></main>'
    ))


def render_user_editor(view_model, flash_message):
    user = view_model["user"]
    form = view_model["form"]
    raw_json = view_model["rawJson"]
    time_zone = view_model["timeZone"]
    flash_html = f'<div class="flash">{escape_html(flash_message)}</div>' if flash_message else ""

    return render_layout(f"Редактор пользователя {user['id']}", (
        '<main class="shell"><section class="hero"><div class="row"><div>'
        f'<h1>Редактор пользователя ID {user["id"]}</h1>'
        '<p class="muted">Максимальное редактирование полей пользователя и raw JSON.</p>'
        f'</div><a href="/"><button class="ghost" type="button">Назад</button></a></div>'
        f'<p class="muted">{escape_html(format_user_name(user))} {"(@" + escape_html(user["username"]) + ")" if user.get("username") else ""}</p>'
        f'<p class="muted">Подписка: {escape_html(format_datetime(user.get("subscriptionUntil"), time_zone) if user.get("subscriptionUntil") else "нет")} | В канале: {escape_html(user.get("channelMemberStatus") or "unknown")}</p>'
        '</section>'
        f'{flash_html}'
        '<section class="split"><article class="card"><h2>Структурированное редактирование</h2>'
        f'<form method="post" action="/users/{user["id"]}/structured">'
        f'<label>Username<input type="text" name="username" value="{escape_html(form["username"])}" /></label>'
        f'<label>First name<input type="text" name="firstName" value="{escape_html(form["firstName"])}" /></label>'
        f'<label>Last name<input type="text" name="lastName" value="{escape_html(form["lastName"])}" /></label>'
        f'<label>Language code<input type="text" name="languageCode" value="{escape_html(form["languageCode"])}" /></label>'
        f'<label>Balance Stars<input type="number" name="balanceStars" value="{escape_html(str(form["balanceStars"]))}" /></label>'
        f'<label>Subscription until<input type="datetime-local" name="subscriptionUntil" value="{escape_html(form["subscriptionUntil"])}" /></label>'
        f'<label>Total spent Stars<input type="number" name="totalSpentStars" value="{escape_html(str(form["totalSpentStars"]))}" /></label>'
        f'<label>Total payments count<input type="number" name="totalPaymentsCount" value="{escape_html(str(form["totalPaymentsCount"]))}" /></label>'
        f'<label>Last payment at<input type="datetime-local" name="lastPaymentAt" value="{escape_html(form["lastPaymentAt"])}" /></label>'
        f'<label>Last warning at<input type="datetime-local" name="lastWarningAt" value="{escape_html(form["lastWarningAt"])}" /></label>'
        f'<label>Last access granted at<input type="datetime-local" name="lastAccessGrantedAt" value="{escape_html(form["lastAccessGrantedAt"])}" /></label>'
        f'<label>Last access revoked at<input type="datetime-local" name="lastAccessRevokedAt" value="{escape_html(form["lastAccessRevokedAt"])}" /></label>'
        '<label>Channel member status<select name="channelMemberStatus">'
        f'<option value="unknown" {selected(form["channelMemberStatus"], "unknown")}>unknown</option>'
        f'<option value="member" {selected(form["channelMemberStatus"], "member")}>member</option>'
        f'<option value="left" {selected(form["channelMemberStatus"], "left")}>left</option>'
        f'<option value="restricted" {selected(form["channelMemberStatus"], "restricted")}>restricted</option>'
        f'<option value="kicked" {selected(form["channelMemberStatus"], "kicked")}>kicked</option>'
        '</select></label>'
        f'<label>Pending join chat ID<input type="text" name="pendingJoinRequestChatId" value="{escape_html(str(form["pendingJoinRequestChatId"]))}" /></label>'
        f'<label>Pending join created at<input type="datetime-local" name="pendingJoinRequestCreatedAt" value="{escape_html(form["pendingJoinRequestCreatedAt"])}" /></label>'
        f'<label>Pending join invite link<input type="text" name="pendingJoinRequestInviteLink" value="{escape_html(form["pendingJoinRequestInviteLink"])}" /></label>'
        f'<label>Notes<textarea name="notes" rows="6">{escape_html(form["notes"])}</textarea></label>'
        '<button type="submit">Сохранить поля</button></form></article>'
        '<article class="card"><h2>Raw JSON</h2>'
        f'<form method="post" action="/users/{user["id"]}/json"><label>User JSON{text_area("json", raw_json, 28)}</label><button class="secondary" type="submit">Сохранить raw JSON</button></form>'
        f'<form method="post" action="/users/{user["id"]}/delete" style="margin-top:12px"><button class="danger" type="submit">Удалить пользователя</button></form>'
        '</article></section></main>'
    ))


class SessionManager:
    def __init__(self, secret):
        self.secret = secret
        self.sessions = {}

    def create_session(self):
        session_id = secrets.token_hex(24)
        self.sessions[session_id] = {"createdAt": __import__("time").time()}
        return f"{session_id}.{create_signature(self.secret, session_id)}"

    def get_session_id(self, raw_cookie_value):
        if not raw_cookie_value:
            return None

        parts = str(raw_cookie_value).split(".", 1)
        if len(parts) != 2:
            return None

        session_id, signature = parts
        if create_signature(self.secret, session_id) != signature:
            return None

        return session_id if session_id in self.sessions else None

    def destroy_session(self, raw_cookie_value):
        session_id = self.get_session_id(raw_cookie_value)
        if session_id:
            self.sessions.pop(session_id, None)


class AdminServer(ThreadingHTTPServer):
    def __init__(self, server_address, handler_class, config, app):
        super().__init__(server_address, handler_class)
        self.config = config
        self.app = app
        self.session_manager = SessionManager(config.session_secret)
        self.flash_message = ""

    def set_flash(self, message):
        self.flash_message = message

    def consume_flash(self):
        message = self.flash_message
        self.flash_message = ""
        return message


class AdminRequestHandler(BaseHTTPRequestHandler):
    server_version = "PythonAdmin/1.0"

    def log_message(self, format_string, *args):
        return

    @property
    def app(self):
        return self.server.app

    def _send_html(self, status_code, html_text):
        data = html_text.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status_code, payload):
        data = to_json_bytes(payload)
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_csv(self, status_code, content):
        data = content.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="users.csv"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location, cookie_header=None):
        self.send_response(302)
        self.send_header("Location", location)
        if cookie_header:
            self.send_header("Set-Cookie", cookie_header)
        self.end_headers()

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length > 0 else b""

    def _read_form(self):
        return parse_form_encoded(self._read_body())

    def _query(self):
        return parse_qs(urlsplit(self.path).query, keep_blank_values=True)

    def _pathname(self):
        return urlsplit(self.path).path

    def _cookies(self):
        return parse_cookies(self.headers.get("Cookie"))

    def _is_authenticated(self):
        cookies = self._cookies()
        return bool(self.server.session_manager.get_session_id(cookies.get("session")))

    def _require_auth(self):
        if self._is_authenticated():
            return True
        self._redirect("/login")
        return False

    def _filters(self):
        query = self._query()
        return {
            "q": query.get("q", [""])[0],
            "status": query.get("status", ["all"])[0]
        }

    def _handle_login(self):
        form = self._read_form()
        credentials = self.app.get_effective_admin_credentials()
        if form.get("username") != credentials["username"] or form.get("password") != credentials["password"]:
            self._send_html(401, render_login("Неверный логин или пароль."))
            return

        session = self.server.session_manager.create_session()
        self._redirect("/", f"session={quote(session)}; Path=/; HttpOnly; SameSite=Lax")

    def _handle_exception(self, error):
        print(f"Admin server error: {error}", flush=True)
        self._send_html(500, "Internal Server Error")

    def do_GET(self):
        try:
            pathname = self._pathname()

            if pathname == "/healthz":
                self._send_json(200, {"ok": True})
                return

            if pathname == "/login":
                self._send_html(200, render_login())
                return

            if not self._require_auth():
                return

            if pathname == "/":
                view_model = self.app.get_admin_view_model(self._filters())
                view_model["flashMessage"] = self.server.consume_flash()
                self._send_html(200, render_dashboard(view_model))
                return

            if pathname == "/api/stats":
                self._send_json(200, self.app.get_admin_view_model(self._filters())["stats"])
                return

            if pathname == "/api/users":
                self._send_json(200, self.app.get_admin_view_model(self._filters())["users"])
                return

            if pathname == "/api/settings":
                self._send_json(200, self.app.get_admin_view_model(self._filters())["settings"])
                return

            if pathname == "/api/state":
                self._send_json(200, self.app.export_state())
                return

            user_page_match = re.match(r"^/users/(\d+)$", pathname)
            if user_page_match:
                view_model = self.app.get_user_editor_view_model(user_page_match.group(1))
                if not view_model:
                    self._send_html(404, "User not found")
                    return
                self._send_html(200, render_user_editor(view_model, self.server.consume_flash()))
                return

            if pathname == "/export/users.csv":
                view_model = self.app.get_admin_view_model(self._filters())
                self._send_csv(200, build_users_csv(view_model["users"], view_model["timeZone"]))
                return

            self._send_html(404, "Not found")
        except Exception as error:
            self._handle_exception(error)

    def do_POST(self):
        try:
            pathname = self._pathname()

            if pathname == "/login":
                self._handle_login()
                return

            if not self._require_auth():
                return

            if pathname == "/logout":
                cookies = self._cookies()
                self.server.session_manager.destroy_session(cookies.get("session"))
                self._redirect("/login", "session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
                return

            if pathname == "/settings":
                form = self._read_form()
                self.app.update_settings({
                    "subscriptionPriceStars": max(1, parse_integer(form.get("subscriptionPriceStars"), 250)),
                    "subscriptionDurationDays": max(1, parse_integer(form.get("subscriptionDurationDays"), 30)),
                    "warningDays": max(1, parse_integer(form.get("warningDays"), 3)),
                    "subscriptionName": form.get("subscriptionName") or "Доступ в приватный канал",
                    "subscriptionDescription": form.get("subscriptionDescription") or "Оплата доступа к приватному Telegram-каналу",
                    "welcomeText": form.get("welcomeText") or "",
                    "supportUsername": form.get("supportUsername") or "",
                    "channelInviteLink": form.get("channelInviteLink") or "",
                    "recurringPaymentsEnabled": parse_boolean_from_form(form.get("recurringPaymentsEnabled"))
                })
                self.server.set_flash("Настройки сохранены.")
                self._redirect("/")
                return

            if pathname == "/settings/system":
                form = self._read_form()
                self.app.update_settings(parse_system_settings(form))
                self.server.set_flash("Системные настройки сохранены.")
                self._redirect("/")
                return

            if pathname == "/actions/invite-link/refresh":
                self._read_body()
                link = self.app.refresh_invite_link()
                self.server.set_flash("Новая ссылка приглашения создана." if link else "Не удалось создать ссылку.")
                self._redirect("/")
                return

            if pathname == "/users/create":
                form = self._read_form()
                user = self.app.create_blank_user(parse_integer(form.get("id"), 0))
                self.server.set_flash(f"Пользователь {user['id']} создан.")
                self._redirect(f"/users/{user['id']}")
                return

            if pathname == "/broadcast":
                form = self._read_form()
                sent_count = self.app.broadcast_users(form.get("scope") or "all", form.get("text") or "")
                self.server.set_flash(f"Рассылка выполнена. Сообщение отправлено: {sent_count}.")
                self._redirect("/")
                return

            if pathname == "/json/settings":
                form = self._read_form()
                self.app.replace_settings_from_json(form.get("json") or "{}")
                self.server.set_flash("Settings JSON сохранён.")
                self._redirect("/")
                return

            if pathname == "/json/templates":
                form = self._read_form()
                self.app.replace_templates_from_json(form.get("json") or "{}")
                self.server.set_flash("Шаблоны сообщений сохранены.")
                self._redirect("/")
                return

            if pathname == "/json/state":
                form = self._read_form()
                self.app.replace_state_from_json(form.get("json") or "{}")
                self.server.set_flash("Полное состояние базы заменено.")
                self._redirect("/")
                return

            balance_match = re.match(r"^/users/(\d+)/balance$", pathname)
            if balance_match:
                form = self._read_form()
                amount = parse_integer(form.get("amount"), 0)
                self.app.adjust_user_balance(balance_match.group(1), amount, form.get("reason") or "admin_balance")
                self.server.set_flash(f"Баланс пользователя {balance_match.group(1)} изменён на {amount} Stars.")
                self._redirect("/")
                return

            grant_match = re.match(r"^/users/(\d+)/subscription$", pathname)
            if grant_match:
                form = self._read_form()
                days = max(1, parse_integer(form.get("days"), 1))
                self.app.grant_user_subscription(grant_match.group(1), days, form.get("reason") or "admin_grant")
                self.server.set_flash(f"Подписка пользователю {grant_match.group(1)} продлена на {days} дн.")
                self._redirect(parse_redirect_back(self._query()))
                return

            notes_match = re.match(r"^/users/(\d+)/notes$", pathname)
            if notes_match:
                form = self._read_form()
                self.app.set_user_notes(notes_match.group(1), form.get("notes") or "")
                self.server.set_flash(f"Заметка пользователя {notes_match.group(1)} сохранена.")
                self._redirect("/")
                return

            structured_match = re.match(r"^/users/(\d+)/structured$", pathname)
            if structured_match:
                form = self._read_form()
                self.app.save_user_structured(structured_match.group(1), form)
                self.server.set_flash(f"Поля пользователя {structured_match.group(1)} сохранены.")
                self._redirect(f"/users/{structured_match.group(1)}")
                return

            user_json_match = re.match(r"^/users/(\d+)/json$", pathname)
            if user_json_match:
                form = self._read_form()
                self.app.replace_user_json(user_json_match.group(1), form.get("json") or "{}")
                self.server.set_flash(f"Raw JSON пользователя {user_json_match.group(1)} сохранён.")
                self._redirect(f"/users/{user_json_match.group(1)}")
                return

            delete_user_match = re.match(r"^/users/(\d+)/delete$", pathname)
            if delete_user_match:
                self._read_body()
                self.app.delete_user(delete_user_match.group(1))
                self.server.set_flash(f"Пользователь {delete_user_match.group(1)} удалён.")
                self._redirect("/")
                return

            message_match = re.match(r"^/users/(\d+)/message$", pathname)
            if message_match:
                form = self._read_form()
                self.app.send_admin_message(message_match.group(1), form.get("text") or "")
                self.server.set_flash(f"Сообщение пользователю {message_match.group(1)} отправлено.")
                self._redirect(parse_redirect_back(self._query()))
                return

            approve_match = re.match(r"^/users/(\d+)/approve$", pathname)
            if approve_match:
                self._read_body()
                approved = self.app.approve_pending_request(approve_match.group(1))
                if approved:
                    self.server.set_flash(f"Заявка пользователя {approve_match.group(1)} одобрена.")
                else:
                    self.server.set_flash(f"У пользователя {approve_match.group(1)} нет активной заявки или подписки.")
                self._redirect(parse_redirect_back(self._query()))
                return

            revoke_match = re.match(r"^/users/(\d+)/revoke$", pathname)
            if revoke_match:
                self._read_body()
                self.app.revoke_user_subscription(revoke_match.group(1), "admin_revoke")
                self.server.set_flash(f"Доступ пользователя {revoke_match.group(1)} снят.")
                self._redirect(parse_redirect_back(self._query()))
                return

            self._send_html(404, "Not found")
        except Exception as error:
            self._handle_exception(error)


def create_admin_server(config, app):
    return AdminServer(("127.0.0.1", config.port), AdminRequestHandler, config, app)

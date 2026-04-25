const http = require("http");
const crypto = require("crypto");
const {
  createSignature,
  escapeHtml,
  formatDateTime,
  formatRelativeDuration,
  formatUserName,
  parseBooleanFromForm,
  parseCookies,
  parseFormEncoded,
  parseInteger,
  readBody,
  toJsonResponse
} = require("./src/lib/utils");

function createSessionManager(secret) {
  const sessions = new Map();

  function createSession() {
    const id = crypto.randomBytes(24).toString("hex");
    sessions.set(id, { createdAt: Date.now() });
    return `${id}.${createSignature(secret, id)}`;
  }

  function getSessionId(rawCookieValue) {
    if (!rawCookieValue) {
      return null;
    }

    const [id, signature] = rawCookieValue.split(".");
    if (!id || !signature) {
      return null;
    }

    if (createSignature(secret, id) !== signature) {
      return null;
    }

    return sessions.has(id) ? id : null;
  }

  function destroySession(rawCookieValue) {
    const id = getSessionId(rawCookieValue);
    if (id) {
      sessions.delete(id);
    }
  }

  return {
    createSession,
    getSessionId,
    destroySession
  };
}

function selected(currentValue, expectedValue) {
  return currentValue === expectedValue ? "selected" : "";
}

function escapeCsv(value) {
  const normalized = String(value ?? "").replaceAll('"', '""');
  return `"${normalized}"`;
}

function buildUsersCsv(users, timeZone) {
  const header = [
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
  ].join(",");

  const rows = users.map((user) => ([
    user.id,
    user.username || "",
    formatUserName(user),
    user.balanceStars || 0,
    user.subscriptionUntil ? formatDateTime(user.subscriptionUntil, timeZone) : "",
    user.channelMemberStatus || "",
    user.pendingJoinRequest ? "yes" : "no",
    user.totalSpentStars || 0,
    user.totalPaymentsCount || 0,
    user.notes || ""
  ].map(escapeCsv).join(",")));

  return [header, ...rows].join("\n");
}

function textArea(name, value, rows = 10) {
  return `<textarea name="${escapeHtml(name)}" rows="${rows}">${escapeHtml(value || "")}</textarea>`;
}

function formatDateTimeLocalValue(timestampMs) {
  if (!timestampMs) {
    return "";
  }

  const date = new Date(timestampMs);
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const min = String(date.getMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}T${hh}:${min}`;
}

function parseRedirectBack(url) {
  const back = url.searchParams.get("back");
  return back && back.startsWith("/") ? back : "/";
}

function parseSystemSettings(form) {
  return {
    botTokenOverride: form.botTokenOverride || "",
    channelId: form.channelId || "",
    appTimezone: form.appTimezone || "",
    adminUsername: form.adminUsername || "",
    adminPassword: form.adminPassword || "",
    pollTimeoutSeconds: Math.max(1, parseInteger(form.pollTimeoutSeconds, 25)),
    serviceCheckIntervalMs: Math.max(10_000, parseInteger(form.serviceCheckIntervalMs, 60_000)),
    autoCreateInviteLink: parseBooleanFromForm(form.autoCreateInviteLink)
  };
}

function renderLayout(title, content) {
  return `<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(title)}</title>
  <style>
    :root {
      --bg: #f3ecdf;
      --panel: rgba(255, 250, 243, 0.96);
      --ink: #16212b;
      --muted: #687482;
      --accent: #0f766e;
      --accent-soft: #d6f0ea;
      --danger: #b42318;
      --danger-soft: #fee7e5;
      --border: #dccfb8;
      --shadow: 0 18px 45px rgba(22, 33, 43, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      font-family: "Segoe UI", Tahoma, sans-serif;
      background:
        radial-gradient(circle at 0% 0%, rgba(15, 118, 110, 0.14), transparent 28%),
        radial-gradient(circle at 100% 0%, rgba(180, 35, 24, 0.10), transparent 22%),
        linear-gradient(180deg, #f8f3ea 0%, #f1e7d6 100%);
    }
    a { color: var(--accent); }
    .shell { width: min(1380px, calc(100vw - 28px)); margin: 20px auto 42px; }
    .hero, .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }
    .hero { padding: 22px; margin-bottom: 18px; }
    .hero-top, .stack-head, .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }
    .hero-search {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) 180px auto auto;
      gap: 10px;
      margin-top: 14px;
    }
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 12px;
      margin: 18px 0;
    }
    .metric {
      padding: 16px;
      border-radius: 18px;
      border: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(244,236,223,0.95));
    }
    .metric strong {
      display: block;
      margin-top: 8px;
      font-size: 30px;
      line-height: 1;
    }
    .grid {
      display: grid;
      grid-template-columns: 380px 1fr;
      gap: 18px;
    }
    .stack {
      display: grid;
      gap: 18px;
    }
    .card { padding: 20px; }
    h1, h2, h3, p { margin: 0; }
    h1 { font-size: 30px; }
    h2 { font-size: 22px; }
    h3 { font-size: 16px; }
    .muted { color: var(--muted); }
    form { display: grid; gap: 10px; }
    label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
    }
    input, textarea, select, button {
      font: inherit;
    }
    input, textarea, select {
      width: 100%;
      border-radius: 14px;
      border: 1px solid #ccbfa7;
      padding: 11px 13px;
      background: #fffdf8;
      color: var(--ink);
    }
    textarea {
      min-height: 88px;
      resize: vertical;
    }
    button {
      border: 0;
      border-radius: 14px;
      padding: 11px 15px;
      cursor: pointer;
      background: var(--accent);
      color: white;
      font-weight: 700;
    }
    button.secondary { background: #27415c; }
    button.ghost {
      background: transparent;
      color: var(--ink);
      border: 1px solid var(--border);
    }
    button.danger { background: var(--danger); }
    .checkbox {
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--ink);
    }
    .checkbox input { width: auto; }
    .flash {
      margin-bottom: 16px;
      border-radius: 16px;
      padding: 12px 14px;
      border: 1px solid #bde5dd;
      background: #e6f7f3;
      color: #0b5a51;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 4px 10px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
    }
    .pill.danger {
      background: var(--danger-soft);
      color: var(--danger);
    }
    .pill.waiting {
      background: #fff0d2;
      color: #9a5c00;
    }
    .toolbar {
      margin-bottom: 12px;
    }
    .table-wrap { overflow: auto; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    th, td {
      border-bottom: 1px solid rgba(204, 191, 167, 0.64);
      text-align: left;
      vertical-align: top;
      padding: 12px 10px;
    }
    th {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }
    .user-actions {
      display: grid;
      gap: 8px;
      min-width: 250px;
    }
    .compact-two {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      align-items: end;
    }
    .compact-three {
      display: grid;
      grid-template-columns: 120px 1fr auto;
      gap: 8px;
      align-items: end;
    }
    .inline-buttons {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .small {
      font-size: 12px;
    }
    .split-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      margin-top: 18px;
    }
    @media (max-width: 1100px) {
      .grid, .split-grid { grid-template-columns: 1fr; }
      .hero-search { grid-template-columns: 1fr; }
      .compact-three, .compact-two, .inline-buttons { grid-template-columns: 1fr; }
      .user-actions { min-width: 220px; }
    }
  </style>
</head>
<body>
  ${content}
</body>
</html>`;
}

function renderLogin(errorText = "") {
  return renderLayout("Вход в админку", `
  <main class="shell" style="max-width:480px;margin-top:72px">
    <section class="card">
      <div class="stack-head">
        <div>
          <h1>Админ-панель</h1>
          <p class="muted">Управление подписчиками, платежами и доступом к каналу.</p>
        </div>
      </div>
      ${errorText ? `<div class="flash" style="background:#fee7e5;border-color:#f5c6c2;color:#8f1d14">${escapeHtml(errorText)}</div>` : ""}
      <form method="post" action="/login">
        <label>Логин<input type="text" name="username" autocomplete="username" required /></label>
        <label>Пароль<input type="password" name="password" autocomplete="current-password" required /></label>
        <button type="submit">Войти</button>
      </form>
    </section>
  </main>`);
}

function renderUserStatus(user, timeZone) {
  if (user.pendingJoinRequest) {
    return `
      <span class="pill waiting">Есть заявка</span><br />
      <span class="muted small">${formatDateTime(user.pendingJoinRequest.createdAt, timeZone)}</span>`;
  }

  if (user.subscriptionUntil && user.subscriptionUntil > Date.now()) {
    return `
      <span class="pill">Активна</span><br />
      <span class="muted small">${formatDateTime(user.subscriptionUntil, timeZone)}</span><br />
      <span class="muted small">${formatRelativeDuration(user.subscriptionUntil)}</span>`;
  }

  if (user.subscriptionUntil) {
    return `
      <span class="pill danger">Истекла</span><br />
      <span class="muted small">${formatDateTime(user.subscriptionUntil, timeZone)}</span>`;
  }

  return `<span class="pill danger">Нет подписки</span>`;
}

function renderDashboard(viewModel) {
  const { stats, settings, system, users, payments, auditLog, flashMessage, timeZone, filters, stateJson, settingsJson, templatesJson } = viewModel;

  const userRows = users.map((user) => {
    const username = user.username ? `@${escapeHtml(user.username)}` : "—";
    const noteValue = escapeHtml(user.notes || "");

    return `
      <tr>
        <td>
          <strong>${escapeHtml(formatUserName(user))}</strong><br />
          <span class="muted">${username}</span><br />
          <span class="muted small">ID ${user.id}</span>
        </td>
        <td>${renderUserStatus(user, timeZone)}</td>
        <td>
          <strong>${user.balanceStars || 0} ⭐</strong><br />
          <span class="muted small">В канале: ${escapeHtml(user.channelMemberStatus || "unknown")}</span><br />
          <span class="muted small">Платежей: ${user.totalPaymentsCount || 0}</span><br />
          <span class="muted small">Потрачено: ${user.totalSpentStars || 0} ⭐</span>
        </td>
        <td class="user-actions">
          <a href="/users/${user.id}" style="display:block"><button class="ghost" type="button">Полный редактор</button></a>
          <form method="post" action="/users/${user.id}/subscription">
            <div class="compact-three">
              <label>Дней<input type="number" name="days" min="1" value="${settings.subscriptionDurationDays}" /></label>
              <label>Причина<input type="text" name="reason" value="admin_grant" /></label>
              <button type="submit">Выдать</button>
            </div>
          </form>
          <form method="post" action="/users/${user.id}/balance">
            <div class="compact-three">
              <label>Баланс<input type="number" name="amount" value="50" /></label>
              <label>Причина<input type="text" name="reason" value="admin_balance" /></label>
              <button class="secondary" type="submit">Изменить</button>
            </div>
          </form>
          <form method="post" action="/users/${user.id}/message">
            <div class="compact-two">
              <label>Сообщение<input type="text" name="text" placeholder="Написать пользователю..." required /></label>
              <button class="secondary" type="submit">Отправить</button>
            </div>
          </form>
          <form method="post" action="/users/${user.id}/notes">
            <label>Заметка<textarea name="notes">${noteValue}</textarea></label>
            <button class="ghost" type="submit">Сохранить заметку</button>
          </form>
          <div class="inline-buttons">
            <form method="post" action="/users/${user.id}/approve">
              <button class="secondary" type="submit">Одобрить заявку</button>
            </form>
            <form method="post" action="/users/${user.id}/revoke">
              <button class="danger" type="submit">Снять доступ</button>
            </form>
          </div>
        </td>
      </tr>`;
  }).join("");

  const paymentRows = payments.map((payment) => `
    <tr>
      <td>${escapeHtml(payment.invoicePayload)}</td>
      <td>ID ${payment.userId}</td>
      <td>${payment.totalAmount} ⭐</td>
      <td>${formatDateTime(payment.paidAt, timeZone)}</td>
    </tr>`).join("");

  const auditRows = auditLog.map((item) => `
    <tr>
      <td>${escapeHtml(item.type)}</td>
      <td>${item.userId ? `ID ${item.userId}` : "—"}</td>
      <td>${escapeHtml(JSON.stringify(item))}</td>
      <td>${formatDateTime(Date.parse(item.createdAt), timeZone)}</td>
    </tr>`).join("");

  return renderLayout("Админ-панель", `
  <main class="shell">
    <section class="hero">
      <div class="hero-top">
        <div>
          <h1>Управление платным каналом</h1>
          <p class="muted">Поиск по подписчикам, ручные действия, рассылка, экспорт и настройки в одном месте.</p>
        </div>
        <form method="post" action="/logout">
          <button class="secondary" type="submit">Выйти</button>
        </form>
      </div>
      <form class="hero-search" method="get" action="/">
        <label>Поиск<input type="text" name="q" value="${escapeHtml(filters.q)}" placeholder="ID, username, имя, заметка" /></label>
        <label>Фильтр
          <select name="status">
            <option value="all" ${selected(filters.status, "all")}>Все</option>
            <option value="active" ${selected(filters.status, "active")}>Активные</option>
            <option value="soon" ${selected(filters.status, "soon")}>Истекают скоро</option>
            <option value="pending" ${selected(filters.status, "pending")}>С заявкой</option>
            <option value="expired" ${selected(filters.status, "expired")}>Истекшие</option>
            <option value="inactive" ${selected(filters.status, "inactive")}>Без подписки</option>
          </select>
        </label>
        <button type="submit">Применить</button>
        <a href="/" style="display:flex"><button class="ghost" type="button">Сбросить</button></a>
      </form>
    </section>

    ${flashMessage ? `<div class="flash">${escapeHtml(flashMessage)}</div>` : ""}

    <section class="cards">
      <article class="metric"><span class="muted">Всего пользователей</span><strong>${stats.totalUsers}</strong></article>
      <article class="metric"><span class="muted">Активные подписки</span><strong>${stats.activeSubscriptions}</strong></article>
      <article class="metric"><span class="muted">Скоро истекают</span><strong>${stats.expiringSoon}</strong></article>
      <article class="metric"><span class="muted">Ожидают одобрения</span><strong>${stats.pendingJoinRequests}</strong></article>
      <article class="metric"><span class="muted">Доход</span><strong>${stats.revenueStars} ⭐</strong></article>
      <article class="metric"><span class="muted">Баланс пользователей</span><strong>${stats.totalBalanceStars} ⭐</strong></article>
      <article class="metric"><span class="muted">Участников в канале</span><strong>${stats.channelMembers}</strong></article>
      <article class="metric"><span class="muted">Recurring</span><strong>${stats.recurringEnabled ? "ON" : "OFF"}</strong></article>
    </section>

    <section class="grid">
      <div class="stack">
        <article class="card">
          <div class="stack-head">
            <div>
              <h2>Базовые настройки</h2>
              <p class="muted">Цена, срок, предупреждение, описание и support username.</p>
            </div>
          </div>
          <form method="post" action="/settings">
            <label>Цена подписки в Stars<input type="number" min="1" name="subscriptionPriceStars" value="${settings.subscriptionPriceStars}" required /></label>
            <label>Длительность подписки в днях<input type="number" min="1" name="subscriptionDurationDays" value="${settings.subscriptionDurationDays}" required /></label>
            <label>Предупреждать за сколько дней<input type="number" min="1" name="warningDays" value="${settings.warningDays}" required /></label>
            <label>Название подписки<input type="text" name="subscriptionName" value="${escapeHtml(settings.subscriptionName)}" required /></label>
            <label>Описание<textarea name="subscriptionDescription" required>${escapeHtml(settings.subscriptionDescription)}</textarea></label>
            <label>Welcome-текст<textarea name="welcomeText">${escapeHtml(settings.welcomeText || "")}</textarea></label>
            <label>Support username<input type="text" name="supportUsername" value="${escapeHtml(settings.supportUsername || "")}" /></label>
            <label>Ссылка на канал<input type="text" name="channelInviteLink" value="${escapeHtml(settings.channelInviteLink || "")}" /></label>
            <label class="checkbox"><input type="checkbox" name="recurringPaymentsEnabled" ${settings.recurringPaymentsEnabled ? "checked" : ""} />Включить recurring-платёж на 30 дней</label>
            <button type="submit">Сохранить настройки</button>
          </form>
        </article>

        <article class="card">
          <div class="stack-head">
            <div>
              <h2>Системные настройки</h2>
              <p class="muted">Токен, канал, таймзона, логин/пароль и интервалы обновления теперь тоже можно менять из админки.</p>
            </div>
          </div>
          <form method="post" action="/settings/system">
            <label>Bot token override<input type="text" name="botTokenOverride" value="${escapeHtml(settings.botTokenOverride || "")}" /></label>
            <label>Channel ID override<input type="text" name="channelId" value="${escapeHtml(settings.channelId || "")}" placeholder="@channel_or_-100..." /></label>
            <label>Timezone<input type="text" name="appTimezone" value="${escapeHtml(settings.appTimezone || system.appTimezone)}" /></label>
            <label>Admin username<input type="text" name="adminUsername" value="${escapeHtml(settings.adminUsername || system.adminUsername)}" /></label>
            <label>Admin password<input type="text" name="adminPassword" value="${escapeHtml(settings.adminPassword || system.adminPassword)}" /></label>
            <label>Poll timeout seconds<input type="number" min="1" name="pollTimeoutSeconds" value="${escapeHtml(String(settings.pollTimeoutSeconds || system.pollTimeoutSeconds))}" /></label>
            <label>Service check interval ms<input type="number" min="10000" step="1000" name="serviceCheckIntervalMs" value="${escapeHtml(String(settings.serviceCheckIntervalMs || system.serviceCheckIntervalMs))}" /></label>
            <label class="checkbox"><input type="checkbox" name="autoCreateInviteLink" ${system.autoCreateInviteLink ? "checked" : ""} />Автоматически создавать invite link</label>
            <button class="secondary" type="submit">Сохранить системные настройки</button>
          </form>
        </article>

        <article class="card">
          <div class="stack-head">
            <div>
              <h2>Служебные действия</h2>
              <p class="muted">Обновление ссылки и экспорт подписчиков.</p>
            </div>
          </div>
          <form method="post" action="/actions/invite-link/refresh">
            <button class="secondary" type="submit">Пересоздать invite link</button>
          </form>
          <form method="post" action="/users/create" style="margin-top:12px">
            <label>Новый user ID<input type="number" name="id" min="1" required /></label>
            <button type="submit">Создать пустого пользователя</button>
          </form>
          <div class="toolbar" style="margin-top:12px">
            <a href="/export/users.csv?q=${encodeURIComponent(filters.q)}&status=${encodeURIComponent(filters.status)}">Скачать CSV пользователей</a>
          </div>
        </article>

        <article class="card">
          <div class="stack-head">
            <div>
              <h2>Массовая рассылка</h2>
              <p class="muted">Можно отправить сообщение всем, активным, истекающим или только тем, у кого есть заявка.</p>
            </div>
          </div>
          <form method="post" action="/broadcast">
            <label>Кому
              <select name="scope">
                <option value="all">Всем</option>
                <option value="active">Только активным</option>
                <option value="soon">Только тем, у кого скоро истечёт</option>
                <option value="pending">Только с заявкой на вступление</option>
                <option value="expired">Только истекшим</option>
              </select>
            </label>
            <label>Текст<textarea name="text" placeholder="Текст сообщения..." required></textarea></label>
            <button type="submit">Отправить рассылку</button>
          </form>
        </article>
      </div>

      <article class="card">
        <div class="stack-head">
          <div>
            <h2>Подписчики</h2>
            <p class="muted">Найдено: ${users.length}. Здесь можно выдать подписку, скорректировать баланс, отправить сообщение и сохранить заметку.</p>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Пользователь</th>
                <th>Статус</th>
                <th>Сводка</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              ${userRows || `<tr><td colspan="4" class="muted">По текущему фильтру пользователей нет.</td></tr>`}
            </tbody>
          </table>
        </div>
      </article>
    </section>

    <section class="split-grid">
      <article class="card">
        <div class="stack-head">
          <div>
            <h2>JSON настроек</h2>
            <p class="muted">Можно редактировать все поля settings и шаблоны сообщений целиком.</p>
          </div>
        </div>
        <form method="post" action="/json/settings">
          <label>Settings JSON
            ${textArea("json", settingsJson, 18)}
          </label>
          <button type="submit">Сохранить settings JSON</button>
        </form>
        <form method="post" action="/json/templates" style="margin-top:14px">
          <label>Message templates JSON
            ${textArea("json", templatesJson, 14)}
          </label>
          <button class="secondary" type="submit">Сохранить шаблоны</button>
        </form>
      </article>

      <article class="card">
        <div class="stack-head">
          <div>
            <h2>Полная база JSON</h2>
            <p class="muted">Здесь можно изменить вообще всё: настройки, пользователей, платежи, аудит и meta.</p>
          </div>
        </div>
        <form method="post" action="/json/state">
          <label>State JSON
            ${textArea("json", stateJson, 26)}
          </label>
          <button class="danger" type="submit">Заменить всё состояние</button>
        </form>
      </article>
    </section>

    <section class="split-grid">
      <article class="card">
        <div class="stack-head">
          <div>
            <h2>Последние платежи</h2>
            <p class="muted">Успешные оплаты из Telegram Stars.</p>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Payload</th>
                <th>Пользователь</th>
                <th>Сумма</th>
                <th>Дата</th>
              </tr>
            </thead>
            <tbody>
              ${paymentRows || `<tr><td colspan="4" class="muted">Платежей пока нет.</td></tr>`}
            </tbody>
          </table>
        </div>
      </article>

      <article class="card">
        <div class="stack-head">
          <div>
            <h2>Аудит</h2>
            <p class="muted">Ручные действия из админки и служебные операции.</p>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Тип</th>
                <th>Пользователь</th>
                <th>Детали</th>
                <th>Дата</th>
              </tr>
            </thead>
            <tbody>
              ${auditRows || `<tr><td colspan="4" class="muted">Аудит пока пуст.</td></tr>`}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  </main>`);
}

function renderUserEditor(viewModel, flashMessage) {
  const { user, form, rawJson, timeZone } = viewModel;

  return renderLayout(`Редактор пользователя ${user.id}`, `
  <main class="shell">
    <section class="hero">
      <div class="hero-top">
        <div>
          <h1>Редактор пользователя ID ${user.id}</h1>
          <p class="muted">Максимальное редактирование полей пользователя и raw JSON.</p>
        </div>
        <a href="/"><button class="ghost" type="button">Назад</button></a>
      </div>
      <p class="muted">${escapeHtml(formatUserName(user))} ${user.username ? `(@${escapeHtml(user.username)})` : ""}</p>
      <p class="muted">Подписка: ${user.subscriptionUntil ? formatDateTime(user.subscriptionUntil, timeZone) : "нет"} | В канале: ${escapeHtml(user.channelMemberStatus || "unknown")}</p>
    </section>

    ${flashMessage ? `<div class="flash">${escapeHtml(flashMessage)}</div>` : ""}

    <section class="split-grid">
      <article class="card">
        <div class="stack-head">
          <div>
            <h2>Структурированное редактирование</h2>
            <p class="muted">Меняйте поля по отдельности.</p>
          </div>
        </div>
        <form method="post" action="/users/${user.id}/structured">
          <label>Username<input type="text" name="username" value="${escapeHtml(form.username)}" /></label>
          <label>First name<input type="text" name="firstName" value="${escapeHtml(form.firstName)}" /></label>
          <label>Last name<input type="text" name="lastName" value="${escapeHtml(form.lastName)}" /></label>
          <label>Language code<input type="text" name="languageCode" value="${escapeHtml(form.languageCode)}" /></label>
          <label>Balance Stars<input type="number" name="balanceStars" value="${escapeHtml(String(form.balanceStars))}" /></label>
          <label>Subscription until<input type="datetime-local" name="subscriptionUntil" value="${escapeHtml(form.subscriptionUntil)}" /></label>
          <label>Total spent Stars<input type="number" name="totalSpentStars" value="${escapeHtml(String(form.totalSpentStars))}" /></label>
          <label>Total payments count<input type="number" name="totalPaymentsCount" value="${escapeHtml(String(form.totalPaymentsCount))}" /></label>
          <label>Last payment at<input type="datetime-local" name="lastPaymentAt" value="${escapeHtml(form.lastPaymentAt)}" /></label>
          <label>Last warning at<input type="datetime-local" name="lastWarningAt" value="${escapeHtml(form.lastWarningAt)}" /></label>
          <label>Last access granted at<input type="datetime-local" name="lastAccessGrantedAt" value="${escapeHtml(form.lastAccessGrantedAt)}" /></label>
          <label>Last access revoked at<input type="datetime-local" name="lastAccessRevokedAt" value="${escapeHtml(form.lastAccessRevokedAt)}" /></label>
          <label>Channel member status
            <select name="channelMemberStatus">
              <option value="unknown" ${selected(form.channelMemberStatus, "unknown")}>unknown</option>
              <option value="member" ${selected(form.channelMemberStatus, "member")}>member</option>
              <option value="left" ${selected(form.channelMemberStatus, "left")}>left</option>
              <option value="restricted" ${selected(form.channelMemberStatus, "restricted")}>restricted</option>
              <option value="kicked" ${selected(form.channelMemberStatus, "kicked")}>kicked</option>
            </select>
          </label>
          <label>Pending join chat ID<input type="text" name="pendingJoinRequestChatId" value="${escapeHtml(String(form.pendingJoinRequestChatId || ""))}" /></label>
          <label>Pending join created at<input type="datetime-local" name="pendingJoinRequestCreatedAt" value="${escapeHtml(form.pendingJoinRequestCreatedAt || "")}" /></label>
          <label>Pending join invite link<input type="text" name="pendingJoinRequestInviteLink" value="${escapeHtml(form.pendingJoinRequestInviteLink || "")}" /></label>
          <label>Notes<textarea name="notes" rows="6">${escapeHtml(form.notes)}</textarea></label>
          <button type="submit">Сохранить поля</button>
        </form>
      </article>

      <article class="card">
        <div class="stack-head">
          <div>
            <h2>Raw JSON</h2>
            <p class="muted">Полная замена объекта пользователя.</p>
          </div>
        </div>
        <form method="post" action="/users/${user.id}/json">
          <label>User JSON
            ${textArea("json", rawJson, 28)}
          </label>
          <button class="secondary" type="submit">Сохранить raw JSON</button>
        </form>
        <form method="post" action="/users/${user.id}/delete" style="margin-top:12px">
          <button class="danger" type="submit">Удалить пользователя</button>
        </form>
      </article>
    </section>
  </main>`);
}

function createAdminServer({ config, app }) {
  const sessionManager = createSessionManager(config.sessionSecret);
  let flashMessage = "";

  function setFlash(message) {
    flashMessage = message;
  }

  function consumeFlash() {
    const current = flashMessage;
    flashMessage = "";
    return current;
  }

  function redirect(res, location) {
    res.writeHead(302, { Location: location });
    res.end();
  }

  function isAuthenticated(req) {
    const cookies = parseCookies(req.headers.cookie);
    return Boolean(sessionManager.getSessionId(cookies.session));
  }

  function withFilters(url) {
    const q = url.searchParams.get("q") || "";
    const status = url.searchParams.get("status") || "all";
    return { q, status };
  }

  async function handleLogin(req, res) {
    const body = await readBody(req);
    const form = parseFormEncoded(body);
    const credentials = app.getEffectiveAdminCredentials();

    if (form.username !== credentials.username || form.password !== credentials.password) {
      res.writeHead(401, { "Content-Type": "text/html; charset=utf-8" });
      res.end(renderLogin("Неверный логин или пароль."));
      return;
    }

    const session = sessionManager.createSession();
    res.writeHead(302, {
      Location: "/",
      "Set-Cookie": `session=${encodeURIComponent(session)}; Path=/; HttpOnly; SameSite=Lax`
    });
    res.end();
  }

  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, config.baseUrl);
      const pathname = url.pathname;

      if (req.method === "GET" && pathname === "/healthz") {
        return toJsonResponse(res, 200, { ok: true });
      }

      if (req.method === "GET" && pathname === "/login") {
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
        res.end(renderLogin());
        return;
      }

      if (req.method === "POST" && pathname === "/login") {
        await handleLogin(req, res);
        return;
      }

      if (!isAuthenticated(req)) {
        redirect(res, "/login");
        return;
      }

      if (req.method === "POST" && pathname === "/logout") {
        const cookies = parseCookies(req.headers.cookie);
        sessionManager.destroySession(cookies.session);
        res.writeHead(302, {
          Location: "/login",
          "Set-Cookie": "session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
        });
        res.end();
        return;
      }

      if (req.method === "GET" && pathname === "/") {
        const filters = withFilters(url);
        const viewModel = app.getAdminViewModel(filters);
        viewModel.flashMessage = consumeFlash();
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
        res.end(renderDashboard(viewModel));
        return;
      }

      if (req.method === "GET" && pathname === "/api/stats") {
        return toJsonResponse(res, 200, app.getAdminViewModel(withFilters(url)).stats);
      }

      if (req.method === "GET" && pathname === "/api/users") {
        return toJsonResponse(res, 200, app.getAdminViewModel(withFilters(url)).users);
      }

      if (req.method === "GET" && pathname === "/api/settings") {
        return toJsonResponse(res, 200, app.getAdminViewModel(withFilters(url)).settings);
      }

      if (req.method === "GET" && pathname === "/api/state") {
        return toJsonResponse(res, 200, app.exportState());
      }

      const userPageMatch = pathname.match(/^\/users\/(\d+)$/);
      if (req.method === "GET" && userPageMatch) {
        const viewModel = app.getUserEditorViewModel(userPageMatch[1]);
        if (!viewModel) {
          res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
          res.end("User not found");
          return;
        }

        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
        res.end(renderUserEditor(viewModel, consumeFlash()));
        return;
      }

      if (req.method === "GET" && pathname === "/export/users.csv") {
        const viewModel = app.getAdminViewModel(withFilters(url));
        const csv = buildUsersCsv(viewModel.users, viewModel.timeZone);
        res.writeHead(200, {
          "Content-Type": "text/csv; charset=utf-8",
          "Content-Disposition": "attachment; filename=\"users.csv\""
        });
        res.end(csv);
        return;
      }

      if (req.method === "POST" && pathname === "/settings") {
        const body = await readBody(req);
        const form = parseFormEncoded(body);

        app.updateSettings({
          subscriptionPriceStars: Math.max(1, parseInteger(form.subscriptionPriceStars, 250)),
          subscriptionDurationDays: Math.max(1, parseInteger(form.subscriptionDurationDays, 30)),
          warningDays: Math.max(1, parseInteger(form.warningDays, 3)),
          subscriptionName: form.subscriptionName || "Доступ в приватный канал",
          subscriptionDescription: form.subscriptionDescription || "Оплата доступа к приватному Telegram-каналу",
          welcomeText: form.welcomeText || "",
          supportUsername: form.supportUsername || "",
          channelInviteLink: form.channelInviteLink || "",
          recurringPaymentsEnabled: parseBooleanFromForm(form.recurringPaymentsEnabled)
        });

        setFlash("Настройки сохранены.");
        redirect(res, "/");
        return;
      }

      if (req.method === "POST" && pathname === "/settings/system") {
        const body = await readBody(req);
        const form = parseFormEncoded(body);
        app.updateSettings(parseSystemSettings(form));
        setFlash("Системные настройки сохранены.");
        redirect(res, "/");
        return;
      }

      if (req.method === "POST" && pathname === "/actions/invite-link/refresh") {
        await readBody(req);
        const link = await app.refreshInviteLink();
        setFlash(link ? "Новая ссылка приглашения создана." : "Не удалось создать ссылку.");
        redirect(res, "/");
        return;
      }

      if (req.method === "POST" && pathname === "/users/create") {
        const body = await readBody(req);
        const form = parseFormEncoded(body);
        const user = app.createBlankUser(parseInteger(form.id, 0));
        setFlash(`Пользователь ${user.id} создан.`);
        redirect(res, `/users/${user.id}`);
        return;
      }

      if (req.method === "POST" && pathname === "/broadcast") {
        const body = await readBody(req);
        const form = parseFormEncoded(body);
        const sentCount = await app.broadcastUsers({
          scope: form.scope || "all",
          text: form.text || ""
        });
        setFlash(`Рассылка выполнена. Сообщение отправлено: ${sentCount}.`);
        redirect(res, "/");
        return;
      }

      if (req.method === "POST" && pathname === "/json/settings") {
        const body = await readBody(req);
        const form = parseFormEncoded(body);
        app.replaceSettingsFromJson(form.json || "{}");
        setFlash("Settings JSON сохранён.");
        redirect(res, "/");
        return;
      }

      if (req.method === "POST" && pathname === "/json/templates") {
        const body = await readBody(req);
        const form = parseFormEncoded(body);
        app.replaceTemplatesFromJson(form.json || "{}");
        setFlash("Шаблоны сообщений сохранены.");
        redirect(res, "/");
        return;
      }

      if (req.method === "POST" && pathname === "/json/state") {
        const body = await readBody(req);
        const form = parseFormEncoded(body);
        app.replaceStateFromJson(form.json || "{}");
        setFlash("Полное состояние базы заменено.");
        redirect(res, "/");
        return;
      }

      const balanceMatch = pathname.match(/^\/users\/(\d+)\/balance$/);
      if (req.method === "POST" && balanceMatch) {
        const body = await readBody(req);
        const form = parseFormEncoded(body);
        const amount = parseInteger(form.amount, 0);
        app.adjustUserBalance(balanceMatch[1], amount, form.reason || "admin_balance");
        setFlash(`Баланс пользователя ${balanceMatch[1]} изменён на ${amount} ⭐.`);
        redirect(res, "/");
        return;
      }

      const grantMatch = pathname.match(/^\/users\/(\d+)\/subscription$/);
      if (req.method === "POST" && grantMatch) {
        const body = await readBody(req);
        const form = parseFormEncoded(body);
        const days = Math.max(1, parseInteger(form.days, 1));
        await app.grantUserSubscription(grantMatch[1], days, form.reason || "admin_grant");
        setFlash(`Подписка пользователю ${grantMatch[1]} продлена на ${days} дн.`);
        redirect(res, parseRedirectBack(url));
        return;
      }

      const notesMatch = pathname.match(/^\/users\/(\d+)\/notes$/);
      if (req.method === "POST" && notesMatch) {
        const body = await readBody(req);
        const form = parseFormEncoded(body);
        app.setUserNotes(notesMatch[1], form.notes || "");
        setFlash(`Заметка пользователя ${notesMatch[1]} сохранена.`);
        redirect(res, "/");
        return;
      }

      const structuredMatch = pathname.match(/^\/users\/(\d+)\/structured$/);
      if (req.method === "POST" && structuredMatch) {
        const body = await readBody(req);
        const form = parseFormEncoded(body);
        app.saveUserStructured(structuredMatch[1], form);
        setFlash(`Поля пользователя ${structuredMatch[1]} сохранены.`);
        redirect(res, `/users/${structuredMatch[1]}`);
        return;
      }

      const userJsonMatch = pathname.match(/^\/users\/(\d+)\/json$/);
      if (req.method === "POST" && userJsonMatch) {
        const body = await readBody(req);
        const form = parseFormEncoded(body);
        app.replaceUserJson(userJsonMatch[1], form.json || "{}");
        setFlash(`Raw JSON пользователя ${userJsonMatch[1]} сохранён.`);
        redirect(res, `/users/${userJsonMatch[1]}`);
        return;
      }

      const deleteUserMatch = pathname.match(/^\/users\/(\d+)\/delete$/);
      if (req.method === "POST" && deleteUserMatch) {
        await readBody(req);
        app.deleteUser(deleteUserMatch[1]);
        setFlash(`Пользователь ${deleteUserMatch[1]} удалён.`);
        redirect(res, "/");
        return;
      }

      const messageMatch = pathname.match(/^\/users\/(\d+)\/message$/);
      if (req.method === "POST" && messageMatch) {
        const body = await readBody(req);
        const form = parseFormEncoded(body);
        await app.sendAdminMessage(messageMatch[1], form.text || "");
        setFlash(`Сообщение пользователю ${messageMatch[1]} отправлено.`);
        redirect(res, parseRedirectBack(url));
        return;
      }

      const approveMatch = pathname.match(/^\/users\/(\d+)\/approve$/);
      if (req.method === "POST" && approveMatch) {
        await readBody(req);
        const approved = await app.approvePendingRequest(approveMatch[1]);
        setFlash(approved ? `Заявка пользователя ${approveMatch[1]} одобрена.` : `У пользователя ${approveMatch[1]} нет активной заявки или подписки.`);
        redirect(res, parseRedirectBack(url));
        return;
      }

      const revokeMatch = pathname.match(/^\/users\/(\d+)\/revoke$/);
      if (req.method === "POST" && revokeMatch) {
        await readBody(req);
        await app.revokeUserSubscription(revokeMatch[1], "admin_revoke");
        setFlash(`Доступ пользователя ${revokeMatch[1]} снят.`);
        redirect(res, parseRedirectBack(url));
        return;
      }

      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Not found");
    } catch (error) {
      console.error("Admin server error:", error);
      res.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Internal Server Error");
    }
  });

  return server;
}

module.exports = {
  createAdminServer
};

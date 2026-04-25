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
} = require("../lib/utils");

function createSessionManager(secret) {
  const sessions = new Map();

  function createSession() {
    const id = crypto.randomBytes(24).toString("hex");
    sessions.set(id, { createdAt: Date.now() });
    const signature = createSignature(secret, id);
    return `${id}.${signature}`;
  }

  function getSessionId(rawCookieValue) {
    if (!rawCookieValue) {
      return null;
    }

    const [id, signature] = rawCookieValue.split(".");
    if (!id || !signature) {
      return null;
    }

    const expected = createSignature(secret, id);
    if (expected !== signature || !sessions.has(id)) {
      return null;
    }

    return id;
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

function renderLayout(title, content) {
  return `<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(title)}</title>
  <style>
    :root {
      --bg: #f5efe3;
      --paper: #fffaf1;
      --ink: #182028;
      --muted: #66717f;
      --accent: #0f766e;
      --accent-soft: #d7f2ec;
      --danger: #b42318;
      --border: #dfd3bf;
      --shadow: 0 14px 40px rgba(24, 32, 40, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.16), transparent 32%),
        radial-gradient(circle at top right, rgba(180, 35, 24, 0.08), transparent 24%),
        linear-gradient(180deg, #f8f3ea 0%, #f3ebdb 100%);
      color: var(--ink);
    }
    .shell { width: min(1280px, calc(100vw - 32px)); margin: 24px auto 48px; }
    .hero, .card {
      background: rgba(255, 250, 241, 0.94);
      border: 1px solid var(--border);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }
    .hero {
      padding: 24px;
      margin-bottom: 20px;
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: center;
      flex-wrap: wrap;
    }
    h1, h2, p { margin: 0; }
    .muted { color: var(--muted); }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin: 20px 0;
    }
    .metric {
      padding: 18px;
      background: linear-gradient(180deg, rgba(255,255,255,0.95), rgba(244,237,225,0.9));
      border-radius: 20px;
      border: 1px solid var(--border);
    }
    .metric strong { display: block; font-size: 32px; line-height: 1.1; margin-top: 8px; }
    .panel-grid { display: grid; grid-template-columns: 360px 1fr; gap: 20px; }
    .card { padding: 20px; overflow: hidden; }
    form { display: grid; gap: 12px; }
    label { display: grid; gap: 6px; font-size: 14px; color: var(--muted); }
    input, textarea, button { font: inherit; }
    input, textarea {
      width: 100%;
      padding: 12px 14px;
      border-radius: 14px;
      border: 1px solid #cbbfa9;
      background: #fffdf8;
      color: var(--ink);
    }
    textarea { min-height: 92px; resize: vertical; }
    .checkbox { display: flex; align-items: center; gap: 10px; color: var(--ink); }
    .checkbox input { width: auto; }
    button {
      border: 0;
      border-radius: 14px;
      padding: 12px 16px;
      background: var(--accent);
      color: white;
      cursor: pointer;
      font-weight: 600;
    }
    button.secondary { background: #25425f; }
    button.danger { background: var(--danger); }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td {
      padding: 12px 10px;
      border-bottom: 1px solid rgba(203, 191, 169, 0.65);
      vertical-align: top;
      text-align: left;
    }
    th {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }
    .row-actions { display: grid; gap: 8px; min-width: 220px; }
    .row-actions form { grid-template-columns: 1fr auto; align-items: end; }
    .row-actions form.single { grid-template-columns: 1fr; }
    .pill {
      display: inline-block;
      border-radius: 999px;
      padding: 4px 10px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
    }
    .pill.danger { background: #fde7e5; color: var(--danger); }
    .split {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }
    .flash {
      margin-bottom: 16px;
      padding: 12px 14px;
      border-radius: 14px;
      background: #e7f7f4;
      border: 1px solid #bce6df;
      color: #08584f;
    }
    .login { width: min(460px, calc(100vw - 32px)); margin: 80px auto; }
    @media (max-width: 980px) {
      .panel-grid { grid-template-columns: 1fr; }
      .row-actions { min-width: 180px; }
      .row-actions form { grid-template-columns: 1fr; }
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
  <main class="login">
    <section class="card">
      <div class="split">
        <div>
          <h1>Админ-панель бота</h1>
          <p class="muted">Вход для управления подписками, балансом и статистикой.</p>
        </div>
      </div>
      ${errorText ? `<div class="flash" style="background:#fde7e5;border-color:#f6c7c2;color:#8f1d14">${escapeHtml(errorText)}</div>` : ""}
      <form method="post" action="/login">
        <label>Логин<input type="text" name="username" autocomplete="username" required /></label>
        <label>Пароль<input type="password" name="password" autocomplete="current-password" required /></label>
        <button type="submit">Войти</button>
      </form>
    </section>
  </main>`);
}

function renderDashboard(viewModel) {
  const { stats, settings, users, payments, auditLog, flashMessage, timeZone } = viewModel;

  const userRows = users.map((user) => {
    const isActive = user.subscriptionUntil && user.subscriptionUntil > Date.now();
    const username = user.username ? `@${escapeHtml(user.username)}` : "—";

    return `
      <tr>
        <td>
          <strong>${escapeHtml(formatUserName(user))}</strong><br />
          <span class="muted">${username}</span><br />
          <span class="muted">ID ${user.id}</span>
        </td>
        <td>${user.balanceStars} ⭐</td>
        <td>
          <span class="pill ${isActive ? "" : "danger"}">${isActive ? "Активна" : "Нет доступа"}</span><br />
          <span class="muted">${formatDateTime(user.subscriptionUntil, timeZone)}</span><br />
          <span class="muted">${formatRelativeDuration(user.subscriptionUntil)}</span>
        </td>
        <td>
          <span class="muted">Статус в канале: ${escapeHtml(user.channelMemberStatus || "unknown")}</span><br />
          <span class="muted">Платежей: ${user.totalPaymentsCount}</span><br />
          <span class="muted">Потрачено: ${user.totalSpentStars} ⭐</span>
        </td>
        <td class="row-actions">
          <form method="post" action="/users/${user.id}/subscription">
            <label>Дней<input type="number" name="days" min="1" value="${settings.subscriptionDurationDays}" /></label>
            <button type="submit">Выдать</button>
          </form>
          <form method="post" action="/users/${user.id}/balance">
            <label>Баланс<input type="number" name="amount" value="50" /></label>
            <button class="secondary" type="submit">Начислить</button>
          </form>
          <form class="single" method="post" action="/users/${user.id}/approve">
            <button class="secondary" type="submit">Одобрить заявку</button>
          </form>
          <form class="single" method="post" action="/users/${user.id}/revoke">
            <button class="danger" type="submit">Снять доступ</button>
          </form>
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
      <div>
        <h1>Управление подписками Telegram-канала</h1>
        <p class="muted">Цена, срок доступа, баланс, пользователи и последние платежи в одном месте.</p>
      </div>
      <form method="post" action="/logout">
        <button class="secondary" type="submit">Выйти</button>
      </form>
    </section>

    ${flashMessage ? `<div class="flash">${escapeHtml(flashMessage)}</div>` : ""}

    <section class="grid">
      <article class="metric"><span class="muted">Всего пользователей</span><strong>${stats.totalUsers}</strong></article>
      <article class="metric"><span class="muted">Активные подписки</span><strong>${stats.activeSubscriptions}</strong></article>
      <article class="metric"><span class="muted">Истекают скоро</span><strong>${stats.expiringSoon}</strong></article>
      <article class="metric"><span class="muted">Доход</span><strong>${stats.revenueStars} ⭐</strong></article>
      <article class="metric"><span class="muted">Баланс пользователей</span><strong>${stats.totalBalanceStars} ⭐</strong></article>
      <article class="metric"><span class="muted">Участников в канале</span><strong>${stats.channelMembers}</strong></article>
    </section>

    <section class="panel-grid">
      <article class="card">
        <div class="split">
          <div>
            <h2>Настройки</h2>
            <p class="muted">Изменения сохраняются сразу в локальную базу.</p>
          </div>
        </div>
        <form method="post" action="/settings">
          <label>Цена подписки в Stars<input type="number" min="1" name="subscriptionPriceStars" value="${settings.subscriptionPriceStars}" required /></label>
          <label>Длительность подписки (дни)<input type="number" min="1" name="subscriptionDurationDays" value="${settings.subscriptionDurationDays}" required /></label>
          <label>Предупреждать за (дни)<input type="number" min="1" name="warningDays" value="${settings.warningDays}" required /></label>
          <label>Название подписки<input type="text" name="subscriptionName" value="${escapeHtml(settings.subscriptionName)}" required /></label>
          <label>Описание подписки<textarea name="subscriptionDescription" required>${escapeHtml(settings.subscriptionDescription)}</textarea></label>
          <label>Welcome-текст<textarea name="welcomeText">${escapeHtml(settings.welcomeText || "")}</textarea></label>
          <label>Username поддержки<input type="text" name="supportUsername" value="${escapeHtml(settings.supportUsername || "")}" /></label>
          <label>Ссылка на канал<input type="text" name="channelInviteLink" value="${escapeHtml(settings.channelInviteLink || "")}" /></label>
          <label class="checkbox"><input type="checkbox" name="recurringPaymentsEnabled" ${settings.recurringPaymentsEnabled ? "checked" : ""} />Включить recurring-платёж на 30 дней</label>
          <button type="submit">Сохранить настройки</button>
        </form>
      </article>

      <article class="card">
        <div class="split">
          <div>
            <h2>Подписчики</h2>
            <p class="muted">Здесь можно выдать доступ, баланс или вручную одобрить запрос.</p>
          </div>
        </div>
        <div style="overflow:auto">
          <table>
            <thead>
              <tr><th>Пользователь</th><th>Баланс</th><th>Подписка</th><th>Активность</th><th>Действия</th></tr>
            </thead>
            <tbody>
              ${userRows || `<tr><td colspan="5" class="muted">Пользователей пока нет.</td></tr>`}
            </tbody>
          </table>
        </div>
      </article>
    </section>

    <section class="panel-grid" style="margin-top:20px">
      <article class="card">
        <div class="split">
          <div>
            <h2>Последние платежи</h2>
            <p class="muted">История успешных оплат из Telegram Stars.</p>
          </div>
        </div>
        <div style="overflow:auto">
          <table>
            <thead>
              <tr><th>Payload</th><th>Пользователь</th><th>Сумма</th><th>Дата</th></tr>
            </thead>
            <tbody>
              ${paymentRows || `<tr><td colspan="4" class="muted">Платежей пока нет.</td></tr>`}
            </tbody>
          </table>
        </div>
      </article>

      <article class="card">
        <div class="split">
          <div>
            <h2>Аудит</h2>
            <p class="muted">Ручные изменения из админки.</p>
          </div>
        </div>
        <div style="overflow:auto">
          <table>
            <thead>
              <tr><th>Тип</th><th>Пользователь</th><th>Детали</th><th>Дата</th></tr>
            </thead>
            <tbody>
              ${auditRows || `<tr><td colspan="4" class="muted">Действий пока нет.</td></tr>`}
            </tbody>
          </table>
        </div>
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

  function isAuthenticated(req) {
    const cookies = parseCookies(req.headers.cookie);
    return Boolean(sessionManager.getSessionId(cookies.session));
  }

  function redirect(res, location) {
    res.writeHead(302, { Location: location });
    res.end();
  }

  function unauthorized(res) {
    res.writeHead(401, { "Content-Type": "text/html; charset=utf-8" });
    res.end(renderLogin("Неверный логин или пароль."));
  }

  async function handleLogin(req, res) {
    const body = await readBody(req);
    const form = parseFormEncoded(body);

    if (form.username !== config.adminUsername || form.password !== config.adminPassword) {
      return unauthorized(res);
    }

    const session = sessionManager.createSession();
    res.writeHead(302, {
      Location: "/",
      "Set-Cookie": `session=${encodeURIComponent(session)}; Path=/; HttpOnly; SameSite=Lax`
    });
    res.end();
  }

  async function handleSettings(req, res) {
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
  }

  async function handleBalance(req, res, userId) {
    const body = await readBody(req);
    const form = parseFormEncoded(body);
    const amount = parseInteger(form.amount, 0);
    app.adjustUserBalance(userId, amount);
    setFlash(`Баланс пользователя ${userId} обновлён на ${amount} ⭐.`);
    redirect(res, "/");
  }

  async function handleGrant(req, res, userId) {
    const body = await readBody(req);
    const form = parseFormEncoded(body);
    const days = Math.max(1, parseInteger(form.days, 1));
    await app.grantUserSubscription(userId, days);
    setFlash(`Подписка пользователю ${userId} продлена на ${days} дн.`);
    redirect(res, "/");
  }

  async function handleApprove(req, res, userId) {
    await readBody(req);
    await app.approvePendingRequest(userId);
    setFlash(`Попытка одобрения заявки для ${userId} выполнена.`);
    redirect(res, "/");
  }

  async function handleRevoke(req, res, userId) {
    await readBody(req);
    await app.revokeUserSubscription(userId);
    setFlash(`Доступ пользователя ${userId} снят.`);
    redirect(res, "/");
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
        const viewModel = app.getAdminViewModel();
        viewModel.flashMessage = consumeFlash();
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
        res.end(renderDashboard(viewModel));
        return;
      }

      if (req.method === "GET" && pathname === "/api/stats") {
        return toJsonResponse(res, 200, app.getAdminViewModel().stats);
      }

      if (req.method === "GET" && pathname === "/api/users") {
        return toJsonResponse(res, 200, app.getAdminViewModel().users);
      }

      if (req.method === "GET" && pathname === "/api/settings") {
        return toJsonResponse(res, 200, app.getAdminViewModel().settings);
      }

      if (req.method === "POST" && pathname === "/settings") {
        await handleSettings(req, res);
        return;
      }

      const balanceMatch = pathname.match(/^\/users\/(\d+)\/balance$/);
      if (req.method === "POST" && balanceMatch) {
        await handleBalance(req, res, balanceMatch[1]);
        return;
      }

      const grantMatch = pathname.match(/^\/users\/(\d+)\/subscription$/);
      if (req.method === "POST" && grantMatch) {
        await handleGrant(req, res, grantMatch[1]);
        return;
      }

      const approveMatch = pathname.match(/^\/users\/(\d+)\/approve$/);
      if (req.method === "POST" && approveMatch) {
        await handleApprove(req, res, approveMatch[1]);
        return;
      }

      const revokeMatch = pathname.match(/^\/users\/(\d+)\/revoke$/);
      if (req.method === "POST" && revokeMatch) {
        await handleRevoke(req, res, revokeMatch[1]);
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

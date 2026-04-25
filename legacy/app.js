const { TelegramClient } = require("./src/telegram/client");
const { createAdminServer } = require("./admin-server");
const { formatDateTime, formatUserName, sleep } = require("./src/lib/utils");

function normalizeSearch(value) {
  return String(value || "").trim().toLowerCase();
}

function toNullableNumber(value) {
  if (value === "" || value === null || value === undefined) {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toNullableText(value) {
  const text = String(value ?? "").trim();
  return text ? text : null;
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

function matchesUserFilter(user, statusFilter, warningDays, now) {
  const isActive = Boolean(user.subscriptionUntil && user.subscriptionUntil > now);
  const warningThreshold = now + warningDays * 24 * 60 * 60 * 1000;
  const expiresSoon = Boolean(isActive && user.subscriptionUntil <= warningThreshold);
  const hasPending = Boolean(user.pendingJoinRequest);
  const hasSubscription = Boolean(user.subscriptionUntil);

  if (statusFilter === "active") {
    return isActive;
  }

  if (statusFilter === "soon") {
    return expiresSoon;
  }

  if (statusFilter === "pending") {
    return hasPending;
  }

  if (statusFilter === "expired") {
    return Boolean(hasSubscription && !isActive);
  }

  if (statusFilter === "inactive") {
    return !isActive && !hasPending;
  }

  return true;
}

class SubscriptionBotApp {
  constructor({ config, store }) {
    this.config = config;
    this.store = store;
    this.telegram = new TelegramClient(config.botToken);
    this.currentBotToken = config.botToken;
    this.adminServer = createAdminServer({ config, app: this });
    this.isStopping = false;
  }

  getSettings() {
    return this.store.getSettings();
  }

  getEffectiveSystemSettings() {
    const settings = this.store.getSettings();
    return {
      botToken: settings.botTokenOverride || this.config.botToken,
      channelId: settings.channelId || this.config.channelId,
      appTimezone: settings.appTimezone || this.config.appTimezone,
      adminUsername: settings.adminUsername || this.config.adminUsername,
      adminPassword: settings.adminPassword || this.config.adminPassword,
      autoCreateInviteLink: typeof settings.autoCreateInviteLink === "boolean"
        ? settings.autoCreateInviteLink
        : this.config.autoCreateInviteLink,
      pollTimeoutSeconds: settings.pollTimeoutSeconds || this.config.pollTimeoutSeconds,
      serviceCheckIntervalMs: settings.serviceCheckIntervalMs || this.config.serviceCheckIntervalMs
    };
  }

  getEffectiveAdminCredentials() {
    const system = this.getEffectiveSystemSettings();
    return {
      username: system.adminUsername,
      password: system.adminPassword
    };
  }

  getTelegram() {
    const { botToken } = this.getEffectiveSystemSettings();
    if (botToken !== this.currentBotToken) {
      this.telegram = new TelegramClient(botToken);
      this.currentBotToken = botToken;
    }
    return this.telegram;
  }

  getTemplateContext(userId, extra = {}) {
    const settings = this.store.getSettings();
    const user = userId ? this.store.getUser(userId) : null;
    const system = this.getEffectiveSystemSettings();
    const supportUsername = settings.supportUsername || "";
    const supportMention = supportUsername
      ? (supportUsername.startsWith("@") ? supportUsername : `@${supportUsername}`)
      : "администратору";

    return {
      userId: user?.id || userId || "",
      fullName: user ? formatUserName(user) : "",
      firstName: user?.firstName || "",
      lastName: user?.lastName || "",
      username: user?.username ? `@${user.username}` : "",
      balanceStars: user?.balanceStars || 0,
      subscriptionName: settings.subscriptionName,
      priceStars: settings.subscriptionPriceStars,
      durationDays: settings.subscriptionDurationDays,
      warningDays: settings.warningDays,
      subscriptionUntil: user?.subscriptionUntil
        ? formatDateTime(user.subscriptionUntil, system.appTimezone)
        : "",
      inviteLink: this.store.getEffectiveInviteLink(this.config.channelInviteLink),
      supportUsername,
      supportMention,
      channelId: system.channelId,
      channelMemberStatus: user?.channelMemberStatus || "",
      ...extra
    };
  }

  renderMessageTemplate(templateName, userId, extra = {}) {
    const templates = this.store.getSettings().messageTemplates || {};
    const template = String(templates[templateName] || "");
    const context = this.getTemplateContext(userId, extra);

    return template.replace(/\{\{(\w+)\}\}/g, (_, key) => {
      const value = context[key];
      return value === undefined || value === null ? "" : String(value);
    });
  }

  async start() {
    await this.getTelegram().deleteWebhook(false).catch((error) => {
      console.warn("Failed to delete webhook:", error.message);
    });

    const botInfo = await this.getTelegram().getMe();
    this.store.setBotInfo(botInfo);
    await this.ensureInviteLink();

    this.adminServer.listen(this.config.port, () => {
      console.log(`Admin panel started at http://localhost:${this.config.port}`);
    });

    this.runMaintenanceLoop().catch((error) => {
      console.error("Maintenance loop failed:", error);
    });

    await this.pollLoop();
  }

  async runMaintenanceLoop() {
    while (!this.isStopping) {
      try {
        await this.runSubscriptionMaintenance();
      } catch (error) {
        console.error("Subscription maintenance failed:", error);
      }

      const { serviceCheckIntervalMs } = this.getEffectiveSystemSettings();
      await sleep(Math.max(10_000, Number(serviceCheckIntervalMs) || 60_000));
    }
  }

  async ensureInviteLink(force = false) {
    const settings = this.store.getSettings();
    const system = this.getEffectiveSystemSettings();
    const existingInviteLink = this.store.getEffectiveInviteLink(this.config.channelInviteLink);

    if (!force && (settings.channelInviteLink || existingInviteLink)) {
      return existingInviteLink;
    }

    if (!system.autoCreateInviteLink) {
      return settings.channelInviteLink || existingInviteLink || "";
    }

    const invite = await this.getTelegram().createChatInviteLink(
      system.channelId,
      "Paid access via bot",
      true
    );

    this.store.setJoinInviteLink(invite.invite_link);
    return invite.invite_link;
  }

  async refreshInviteLink() {
    const link = await this.ensureInviteLink(true);
    this.store.addAuditLog({
      type: "refresh_invite_link"
    });
    return link;
  }

  getAdminViewModel(filters = {}) {
    const settings = this.store.getSettings();
    const system = this.getEffectiveSystemSettings();
    const now = Date.now();
    const query = normalizeSearch(filters.q);
    const statusFilter = filters.status || "all";
    const users = this.store.listUsers().filter((user) => {
      const haystack = normalizeSearch([
        user.id,
        user.username,
        user.firstName,
        user.lastName,
        user.notes
      ].join(" "));

      const matchesQuery = !query || haystack.includes(query);
      const matchesStatus = matchesUserFilter(user, statusFilter, settings.warningDays, now);
      return matchesQuery && matchesStatus;
    });

    return {
      stats: this.store.getDashboardStats(),
      settings,
      system,
      users,
      payments: this.store.getPayments().slice(0, 20),
      auditLog: this.store.getAuditLog(20),
      timeZone: system.appTimezone,
      filters: {
        q: filters.q || "",
        status: statusFilter
      },
      stateJson: JSON.stringify(this.store.getState(), null, 2),
      settingsJson: JSON.stringify(settings, null, 2),
      templatesJson: JSON.stringify(settings.messageTemplates || {}, null, 2)
    };
  }

  getUserEditorViewModel(userId) {
    const user = this.store.getUser(userId);
    if (!user) {
      return null;
    }

    return {
      user,
      timeZone: this.getEffectiveSystemSettings().appTimezone,
      rawJson: JSON.stringify(user, null, 2),
      form: {
        id: String(user.id),
        username: user.username || "",
        firstName: user.firstName || "",
        lastName: user.lastName || "",
        languageCode: user.languageCode || "",
        balanceStars: user.balanceStars || 0,
        subscriptionUntil: formatDateTimeLocalValue(user.subscriptionUntil),
        totalSpentStars: user.totalSpentStars || 0,
        totalPaymentsCount: user.totalPaymentsCount || 0,
        lastPaymentAt: formatDateTimeLocalValue(user.lastPaymentAt),
        lastWarningAt: formatDateTimeLocalValue(user.lastWarningAt),
        lastAccessGrantedAt: formatDateTimeLocalValue(user.lastAccessGrantedAt),
        lastAccessRevokedAt: formatDateTimeLocalValue(user.lastAccessRevokedAt),
        channelMemberStatus: user.channelMemberStatus || "unknown",
        notes: user.notes || "",
        pendingJoinRequestChatId: user.pendingJoinRequest?.chatId || "",
        pendingJoinRequestCreatedAt: formatDateTimeLocalValue(user.pendingJoinRequest?.createdAt),
        pendingJoinRequestInviteLink: user.pendingJoinRequest?.inviteLink || ""
      }
    };
  }

  createBlankUser(userId) {
    return this.store.replaceUser(userId, {
      id: Number(userId),
      username: "",
      firstName: "",
      lastName: "",
      languageCode: "",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      balanceStars: 0,
      subscriptionUntil: null,
      totalSpentStars: 0,
      totalPaymentsCount: 0,
      lastPaymentAt: null,
      lastWarningAt: null,
      lastAccessGrantedAt: null,
      lastAccessRevokedAt: null,
      pendingJoinRequest: null,
      channelMemberStatus: "unknown",
      notes: ""
    });
  }

  saveUserStructured(userId, form) {
    const pendingJoinRequestCreatedAt = toNullableText(form.pendingJoinRequestCreatedAt)
      ? new Date(form.pendingJoinRequestCreatedAt).getTime()
      : null;

    const pendingJoinRequest = toNullableText(form.pendingJoinRequestChatId) || toNullableText(form.pendingJoinRequestInviteLink) || pendingJoinRequestCreatedAt
      ? {
          chatId: toNullableText(form.pendingJoinRequestChatId) || "",
          createdAt: pendingJoinRequestCreatedAt || Date.now(),
          inviteLink: toNullableText(form.pendingJoinRequestInviteLink) || ""
        }
      : null;

    return this.store.updateUserFields(userId, {
      username: String(form.username || "").trim(),
      firstName: String(form.firstName || "").trim(),
      lastName: String(form.lastName || "").trim(),
      languageCode: String(form.languageCode || "").trim(),
      balanceStars: Number(form.balanceStars || 0),
      subscriptionUntil: toNullableText(form.subscriptionUntil) ? new Date(form.subscriptionUntil).getTime() : null,
      totalSpentStars: Number(form.totalSpentStars || 0),
      totalPaymentsCount: Number(form.totalPaymentsCount || 0),
      lastPaymentAt: toNullableText(form.lastPaymentAt) ? new Date(form.lastPaymentAt).getTime() : null,
      lastWarningAt: toNullableText(form.lastWarningAt) ? new Date(form.lastWarningAt).getTime() : null,
      lastAccessGrantedAt: toNullableText(form.lastAccessGrantedAt) ? new Date(form.lastAccessGrantedAt).getTime() : null,
      lastAccessRevokedAt: toNullableText(form.lastAccessRevokedAt) ? new Date(form.lastAccessRevokedAt).getTime() : null,
      channelMemberStatus: String(form.channelMemberStatus || "unknown").trim() || "unknown",
      notes: String(form.notes || "").trim(),
      pendingJoinRequest
    });
  }

  replaceUserJson(userId, jsonText) {
    const parsed = JSON.parse(jsonText);
    return this.store.replaceUser(userId, parsed);
  }

  deleteUser(userId) {
    return this.store.deleteUser(userId);
  }

  exportState() {
    return this.store.getState();
  }

  replaceStateFromJson(jsonText) {
    const parsed = JSON.parse(jsonText);
    return this.store.replaceState(parsed);
  }

  replaceSettingsFromJson(jsonText) {
    const parsed = JSON.parse(jsonText);
    return this.store.replaceSettings(parsed);
  }

  replaceTemplatesFromJson(jsonText) {
    const parsed = JSON.parse(jsonText);
    return this.store.updateSettings({
      messageTemplates: parsed
    });
  }

  updateSettings(partialSettings) {
    this.store.addAuditLog({
      type: "settings_update",
      payload: partialSettings
    });
    return this.store.updateSettings(partialSettings);
  }

  adjustUserBalance(userId, amount, reason = "admin_balance") {
    return this.store.adjustBalance(userId, amount, reason);
  }

  async grantUserSubscription(userId, days, reason = "admin_grant") {
    const user = this.store.grantSubscriptionDays(userId, days, reason);
    if (user) {
      await this.notifyUser(user.id, this.renderMessageTemplate("adminGrant", user.id)).catch(() => {});
    }
    return user;
  }

  async revokeUserSubscription(userId, reason = "admin_revoke") {
    const user = this.store.revokeSubscription(userId, reason);
    if (user) {
      await this.removeUserFromChannel(user.id).catch(() => {});
      await this.notifyUser(user.id, this.renderMessageTemplate("adminRevoke", user.id)).catch(() => {});
    }
    return user;
  }

  setUserNotes(userId, notes) {
    return this.store.setUserNotes(userId, notes);
  }

  async sendAdminMessage(userId, text) {
    const cleanedText = String(text || "").trim();
    if (!cleanedText) {
      return false;
    }

    await this.notifyUser(userId, cleanedText);
    this.store.addAuditLog({
      type: "admin_message",
      userId: Number(userId),
      text: cleanedText
    });
    return true;
  }

  async broadcastUsers({ scope, text }) {
    const cleanedText = String(text || "").trim();
    if (!cleanedText) {
      return 0;
    }

    const settings = this.store.getSettings();
    const now = Date.now();
    const candidates = this.store.listUsers().filter((user) => matchesUserFilter(user, scope || "all", settings.warningDays, now));

    let sentCount = 0;
    for (const user of candidates) {
      try {
        await this.notifyUser(user.id, cleanedText);
        sentCount += 1;
      } catch (error) {
        console.warn(`Broadcast failed for ${user.id}:`, error.message);
      }
    }

    this.store.addAuditLog({
      type: "broadcast",
      scope: scope || "all",
      sentCount
    });

    return sentCount;
  }

  async approvePendingRequest(userId) {
    const user = this.store.getUser(userId);
    if (!user?.pendingJoinRequest || !this.store.isSubscriptionActive(user.id)) {
      return false;
    }

    const { channelId } = this.getEffectiveSystemSettings();
    await this.getTelegram().approveChatJoinRequest(channelId, user.id);
    this.store.clearUserPendingJoinRequest(user.id);
    this.store.setUserChannelMemberStatus(user.id, "member");
    await this.notifyUser(user.id, this.renderMessageTemplate("joinApproved", user.id)).catch(() => {});
    return true;
  }

  async pollLoop() {
    const allowedUpdates = [
      "message",
      "callback_query",
      "pre_checkout_query",
      "chat_join_request",
      "chat_member",
      "my_chat_member"
    ];

    while (!this.isStopping) {
      try {
        const offset = (this.store.getMeta().lastUpdateId || 0) + 1;
        const { pollTimeoutSeconds } = this.getEffectiveSystemSettings();
        const updates = await this.getTelegram().getUpdates(
          offset,
          pollTimeoutSeconds,
          allowedUpdates
        );

        for (const update of updates) {
          await this.handleUpdate(update);
          this.store.setLastUpdateId(update.update_id);
        }
      } catch (error) {
        console.error("Polling error:", error);
        await sleep(3000);
      }
    }
  }

  async handleUpdate(update) {
    try {
      if (update.message) {
        await this.handleMessage(update.message);
      } else if (update.callback_query) {
        await this.handleCallbackQuery(update.callback_query);
      } else if (update.pre_checkout_query) {
        await this.handlePreCheckoutQuery(update.pre_checkout_query);
      } else if (update.chat_join_request) {
        await this.handleChatJoinRequest(update.chat_join_request);
      } else if (update.chat_member) {
        await this.handleChatMember(update.chat_member);
      } else if (update.my_chat_member) {
        await this.ensureInviteLink().catch(() => {});
      }
    } catch (error) {
      console.error("Update handling failed:", error, update);
    }
  }

  async handleMessage(message) {
    if (message.from) {
      this.store.ensureUser(message.from);
    }

    if (message.successful_payment) {
      await this.handleSuccessfulPayment(message);
      return;
    }

    if (message.chat?.type !== "private" || !message.text) {
      return;
    }

    const text = message.text.trim();
    const [command, parameter] = text.split(/\s+/, 2);

    if (command === "/start") {
      if (parameter === "buy") {
        await this.sendInvoice(message.from.id);
      } else {
        await this.sendMainMenu(message.from.id);
      }
      return;
    }

    if (command === "/buy") {
      await this.sendInvoice(message.from.id);
      return;
    }

    if (command === "/status") {
      await this.sendStatusMessage(message.from.id);
      return;
    }

    if (command === "/help") {
      await this.sendMainMenu(message.from.id);
      return;
    }

    if (command === "/paysupport") {
      await this.notifyUser(message.from.id, this.renderMessageTemplate("support", message.from.id));
      return;
    }

    await this.sendMainMenu(message.from.id);
  }

  async handleCallbackQuery(callbackQuery) {
    const userId = callbackQuery.from.id;
    this.store.ensureUser(callbackQuery.from);

    if (callbackQuery.data === "buy") {
      await this.sendInvoice(userId);
      await this.getTelegram().answerCallbackQuery(callbackQuery.id, "Счёт отправлен.");
      return;
    }

    if (callbackQuery.data === "status") {
      await this.sendStatusMessage(userId);
      await this.getTelegram().answerCallbackQuery(callbackQuery.id, "Статус обновлён.");
      return;
    }

    if (callbackQuery.data === "join") {
      await this.sendJoinLink(userId);
      await this.getTelegram().answerCallbackQuery(callbackQuery.id, "Проверяю доступ.");
      return;
    }

    if (callbackQuery.data === "buy_balance") {
      const result = this.store.purchaseWithBalance(userId, this.store.getSettings());
      if (!result.ok) {
        await this.getTelegram().answerCallbackQuery(callbackQuery.id, "Недостаточно баланса.");
        await this.notifyUser(userId, "На балансе недостаточно Stars для продления.");
        return;
      }

      await this.getTelegram().answerCallbackQuery(callbackQuery.id, "Подписка оплачена с баланса.");
      await this.notifyUser(
        userId,
        `Подписка продлена с внутреннего баланса до <b>${this.getTemplateContext(userId).subscriptionUntil}</b>.`
      );
      await this.sendJoinLink(userId);
      return;
    }

    await this.getTelegram().answerCallbackQuery(callbackQuery.id, "Команда обработана.");
  }

  async handlePreCheckoutQuery(preCheckoutQuery) {
    const isValid = preCheckoutQuery.invoice_payload.startsWith("subscription:");
    await this.getTelegram().answerPreCheckoutQuery(
      preCheckoutQuery.id,
      isValid,
      isValid ? "" : "Не удалось обработать оплату."
    );
  }

  async handleSuccessfulPayment(message) {
    const user = this.store.ensureUser(message.from);
    const payment = {
      userId: user.id,
      paidAt: (message.date || Math.floor(Date.now() / 1000)) * 1000,
      currency: message.successful_payment.currency,
      totalAmount: message.successful_payment.total_amount,
      invoicePayload: message.successful_payment.invoice_payload,
      subscriptionExpirationDate: message.successful_payment.subscription_expiration_date
        ? message.successful_payment.subscription_expiration_date * 1000
        : null,
      telegramPaymentChargeId: message.successful_payment.telegram_payment_charge_id,
      providerPaymentChargeId: message.successful_payment.provider_payment_charge_id || ""
    };

    if (this.store.hasPayment(payment.telegramPaymentChargeId)) {
      return;
    }

    this.store.recordPayment(payment);
    this.store.activateSubscriptionFromPayment(user.id, payment, this.store.getSettings());

    await this.notifyUser(user.id, this.renderMessageTemplate("paymentReceived", user.id));
    await this.approvePendingRequest(user.id).catch(() => {});
    await this.sendJoinLink(user.id);
  }

  async handleChatJoinRequest(request) {
    const { channelId } = this.getEffectiveSystemSettings();
    const channelIdMatches =
      String(request.chat.id) === String(channelId) ||
      request.chat.username === String(channelId).replace("@", "");

    if (!channelIdMatches) {
      return;
    }

    const user = this.store.ensureUser(request.from);
    this.store.setUserPendingJoinRequest(user.id, {
      chatId: request.chat.id,
      createdAt: Date.now(),
      inviteLink: request.invite_link?.invite_link || ""
    });

    if (this.store.isSubscriptionActive(user.id)) {
      await this.approvePendingRequest(user.id);
      return;
    }

    await this.notifyUser(user.id, this.renderMessageTemplate("joinPending", user.id));
  }

  async handleChatMember(chatMemberUpdate) {
    const user = chatMemberUpdate.new_chat_member?.user;
    if (!user || user.is_bot) {
      return;
    }

    this.store.ensureUser(user);
    this.store.setUserChannelMemberStatus(user.id, chatMemberUpdate.new_chat_member.status);
  }

  async runSubscriptionMaintenance() {
    const settings = this.store.getSettings();
    const system = this.getEffectiveSystemSettings();
    const users = this.store.listUsers();
    const now = Date.now();
    const warningThresholdMs = settings.warningDays * 24 * 60 * 60 * 1000;
    const pendingTtlMs = 7 * 24 * 60 * 60 * 1000;

    for (const user of users) {
      const isActive = Boolean(user.subscriptionUntil && user.subscriptionUntil > now);

      if (isActive) {
        const expiresSoon = user.subscriptionUntil - now <= warningThresholdMs;
        const alreadyWarned = Boolean(
          user.lastWarningAt && user.lastWarningAt > (user.subscriptionUntil - warningThresholdMs)
        );

        if (expiresSoon && !alreadyWarned) {
          await this.notifyUser(user.id, this.renderMessageTemplate("subscriptionExpiring", user.id)).catch(() => {});
          this.store.markWarningSent(user.id);
        }

        continue;
      }

      if (user.subscriptionUntil && (!user.lastAccessRevokedAt || user.lastAccessRevokedAt < user.subscriptionUntil)) {
        await this.removeUserFromChannel(user.id).catch(() => {});
        this.store.markAccessRevoked(user.id);
        await this.notifyUser(user.id, this.renderMessageTemplate("subscriptionExpired", user.id)).catch(() => {});
      }

      if (user.pendingJoinRequest?.createdAt && now - user.pendingJoinRequest.createdAt > pendingTtlMs) {
        await this.getTelegram().declineChatJoinRequest(system.channelId, user.id).catch(() => {});
        this.store.clearUserPendingJoinRequest(user.id);
      }
    }
  }

  async sendMainMenu(userId) {
    const settings = this.store.getSettings();
    const system = this.getEffectiveSystemSettings();
    const user = this.store.getUser(userId);
    const isActive = this.store.isSubscriptionActive(userId);
    const inviteLink = this.store.getEffectiveInviteLink(this.config.channelInviteLink);
    const recurringLabel = settings.recurringPaymentsEnabled
      ? "Автопродление каждые 30 дней: включено."
      : "Оплата разовая, продление вручную.";
    const balanceLine = user ? `Баланс: <b>${user.balanceStars} ⭐</b>.` : "";
    const expiryLine = isActive && user?.subscriptionUntil
      ? `Доступ активен до <b>${formatDateTime(user.subscriptionUntil, system.appTimezone)}</b>.`
      : "Подписка пока не активна.";

    const text = [
      `<b>${settings.subscriptionName}</b>`,
      settings.welcomeText,
      "",
      `Цена: <b>${settings.subscriptionPriceStars} ⭐</b>`,
      `Срок доступа: <b>${settings.subscriptionDurationDays} дней</b>`,
      recurringLabel,
      balanceLine,
      expiryLine,
      inviteLink ? "После оплаты я пришлю ссылку на канал и сам одобрю заявку на вступление." : "После оплаты я активирую доступ."
    ].filter(Boolean).join("\n");

    const buttons = [
      [{ text: "Купить доступ", callback_data: "buy" }],
      [{ text: "Мой статус", callback_data: "status" }, { text: "Вступить в канал", callback_data: "join" }]
    ];

    if ((user?.balanceStars || 0) >= settings.subscriptionPriceStars) {
      buttons.push([{ text: "Оплатить с баланса", callback_data: "buy_balance" }]);
    }

    await this.getTelegram().sendMessage(userId, text, {
      reply_markup: { inline_keyboard: buttons }
    });
  }

  async sendStatusMessage(userId) {
    const settings = this.store.getSettings();
    const system = this.getEffectiveSystemSettings();
    const user = this.store.getUser(userId);

    if (!user) {
      await this.sendMainMenu(userId);
      return;
    }

    const active = this.store.isSubscriptionActive(userId);
    const text = active
      ? [
          `<b>Статус подписки</b>`,
          `Подписка активна до <b>${formatDateTime(user.subscriptionUntil, system.appTimezone)}</b>.`,
          `Баланс: <b>${user.balanceStars} ⭐</b>.`,
          `Статус в канале: <b>${user.channelMemberStatus}</b>.`,
          `Чтобы продлить подписку, цена сейчас ${settings.subscriptionPriceStars} ⭐.`
        ].join("\n")
      : [
          `<b>Статус подписки</b>`,
          "Активной подписки сейчас нет.",
          `Баланс: <b>${user.balanceStars} ⭐</b>.`,
          `Цена подписки: <b>${settings.subscriptionPriceStars} ⭐</b>.`
        ].join("\n");

    await this.getTelegram().sendMessage(userId, text, {
      reply_markup: {
        inline_keyboard: [
          [{ text: "Купить доступ", callback_data: "buy" }],
          [{ text: "Вступить в канал", callback_data: "join" }]
        ]
      }
    });
  }

  async sendInvoice(userId) {
    const settings = this.store.getSettings();
    const payload = `subscription:${userId}:${Date.now()}`;
    const invoice = {
      chat_id: userId,
      title: settings.subscriptionName,
      description: settings.subscriptionDescription,
      payload,
      provider_token: "",
      currency: "XTR",
      prices: [{ label: settings.subscriptionName, amount: settings.subscriptionPriceStars }],
      start_parameter: `sub_${userId}`,
      reply_markup: {
        inline_keyboard: [[{ text: `Оплатить ${settings.subscriptionPriceStars} XTR`, pay: true }]]
      }
    };

    if (settings.recurringPaymentsEnabled) {
      invoice.subscription_period = 2_592_000;
    }

    await this.getTelegram().sendInvoice(invoice);
  }

  async sendJoinLink(userId) {
    if (!this.store.isSubscriptionActive(userId)) {
      await this.notifyUser(userId, this.renderMessageTemplate("noSubscription", userId));
      return;
    }

    const inviteLink = this.store.getEffectiveInviteLink(this.config.channelInviteLink) || await this.ensureInviteLink();
    if (!inviteLink) {
      await this.notifyUser(userId, this.renderMessageTemplate("noInviteLink", userId));
      return;
    }

    await this.notifyUser(
      userId,
      this.renderMessageTemplate("joinInstructions", userId, { inviteLink })
    );
  }

  async removeUserFromChannel(userId) {
    const { channelId } = this.getEffectiveSystemSettings();
    await this.getTelegram().banChatMember(channelId, userId).catch(() => {});
    await this.getTelegram().unbanChatMember(channelId, userId).catch(() => {});
    this.store.setUserChannelMemberStatus(userId, "left");
  }

  async notifyUser(userId, text) {
    return this.getTelegram().sendMessage(userId, text, {
      disable_web_page_preview: true
    });
  }
}

module.exports = {
  SubscriptionBotApp
};

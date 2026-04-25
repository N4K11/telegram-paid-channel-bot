const fs = require("fs");
const path = require("path");
const { addDays, nowIso } = require("./utils");

function createDefaultState() {
  return {
    meta: {
      createdAt: nowIso(),
      updatedAt: nowIso(),
      lastUpdateId: 0,
      botInfo: null,
      joinInviteLink: "",
      joinInviteLinkCreatedAt: null
    },
    settings: {
      subscriptionPriceStars: 250,
      subscriptionDurationDays: 30,
      warningDays: 3,
      recurringPaymentsEnabled: false,
      subscriptionName: "Доступ в приватный канал",
      subscriptionDescription: "Оплата доступа к приватному Telegram-каналу",
      supportUsername: "",
      welcomeText: "Оформите подписку, и бот выдаст доступ в приватный канал.",
      channelInviteLink: ""
    },
    users: {},
    payments: {},
    auditLog: []
  };
}

class JsonStore {
  constructor(filePath) {
    this.filePath = filePath;
    this.tempFilePath = `${filePath}.tmp`;
    this.ensureFile();
    this.state = this.load();
  }

  ensureFile() {
    fs.mkdirSync(path.dirname(this.filePath), { recursive: true });

    if (!fs.existsSync(this.filePath)) {
      fs.writeFileSync(this.filePath, JSON.stringify(createDefaultState(), null, 2), "utf8");
    }
  }

  load() {
    const raw = fs.readFileSync(this.filePath, "utf8");
    const parsed = JSON.parse(raw);
    return {
      ...createDefaultState(),
      ...parsed,
      meta: {
        ...createDefaultState().meta,
        ...(parsed.meta || {})
      },
      settings: {
        ...createDefaultState().settings,
        ...(parsed.settings || {})
      },
      users: parsed.users || {},
      payments: parsed.payments || {},
      auditLog: parsed.auditLog || []
    };
  }

  save() {
    this.state.meta.updatedAt = nowIso();
    fs.writeFileSync(this.tempFilePath, JSON.stringify(this.state, null, 2), "utf8");
    fs.renameSync(this.tempFilePath, this.filePath);
  }

  getMeta() {
    return structuredClone(this.state.meta);
  }

  getSettings() {
    return structuredClone(this.state.settings);
  }

  updateSettings(partialSettings) {
    this.state.settings = {
      ...this.state.settings,
      ...partialSettings
    };
    this.save();
    return this.getSettings();
  }

  addAuditLog(entry) {
    this.state.auditLog.unshift({
      id: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
      createdAt: nowIso(),
      ...entry
    });
    this.state.auditLog = this.state.auditLog.slice(0, 500);
    this.save();
  }

  getAuditLog(limit = 30) {
    return structuredClone(this.state.auditLog.slice(0, limit));
  }

  ensureUser(telegramUser) {
    const userId = String(telegramUser.id);
    const existing = this.state.users[userId] || {
      id: telegramUser.id,
      username: "",
      firstName: "",
      lastName: "",
      languageCode: "",
      createdAt: nowIso(),
      updatedAt: nowIso(),
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
    };

    existing.username = telegramUser.username || existing.username || "";
    existing.firstName = telegramUser.first_name || telegramUser.firstName || existing.firstName || "";
    existing.lastName = telegramUser.last_name || telegramUser.lastName || existing.lastName || "";
    existing.languageCode = telegramUser.language_code || telegramUser.languageCode || existing.languageCode || "";
    existing.updatedAt = nowIso();

    this.state.users[userId] = existing;
    this.save();
    return structuredClone(existing);
  }

  getUser(userId) {
    const user = this.state.users[String(userId)];
    return user ? structuredClone(user) : null;
  }

  listUsers() {
    return Object.values(this.state.users)
      .map((user) => structuredClone(user))
      .sort((left, right) => {
        const leftTs = left.subscriptionUntil || 0;
        const rightTs = right.subscriptionUntil || 0;
        return rightTs - leftTs || right.id - left.id;
      });
  }

  getPayments() {
    return Object.values(this.state.payments)
      .map((payment) => structuredClone(payment))
      .sort((left, right) => right.paidAt - left.paidAt);
  }

  hasPayment(chargeId) {
    return Boolean(this.state.payments[chargeId]);
  }

  recordPayment(payment) {
    this.state.payments[payment.telegramPaymentChargeId] = payment;
    const user = this.state.users[String(payment.userId)];

    if (user) {
      user.totalSpentStars += payment.totalAmount;
      user.totalPaymentsCount += 1;
      user.lastPaymentAt = payment.paidAt;
      user.updatedAt = nowIso();
    }

    this.save();
  }

  setUserPendingJoinRequest(userId, pendingJoinRequest) {
    const user = this.state.users[String(userId)];
    if (!user) {
      return null;
    }

    user.pendingJoinRequest = pendingJoinRequest;
    user.updatedAt = nowIso();
    this.save();
    return structuredClone(user);
  }

  clearUserPendingJoinRequest(userId) {
    return this.setUserPendingJoinRequest(userId, null);
  }

  setUserChannelMemberStatus(userId, status) {
    const user = this.state.users[String(userId)];
    if (!user) {
      return null;
    }

    user.channelMemberStatus = status;
    user.updatedAt = nowIso();
    this.save();
    return structuredClone(user);
  }

  setBotInfo(botInfo) {
    this.state.meta.botInfo = botInfo;
    this.save();
  }

  setLastUpdateId(lastUpdateId) {
    this.state.meta.lastUpdateId = lastUpdateId;
    this.save();
  }

  setJoinInviteLink(inviteLink) {
    this.state.meta.joinInviteLink = inviteLink;
    this.state.meta.joinInviteLinkCreatedAt = nowIso();
    this.save();
  }

  getEffectiveInviteLink(fallbackInviteLink = "") {
    return this.state.settings.channelInviteLink || this.state.meta.joinInviteLink || fallbackInviteLink || "";
  }

  isSubscriptionActive(userId, currentTimeMs = Date.now()) {
    const user = this.state.users[String(userId)];
    return Boolean(user?.subscriptionUntil && user.subscriptionUntil > currentTimeMs);
  }

  activateSubscriptionFromPayment(userId, payment, settings) {
    const user = this.state.users[String(userId)];
    if (!user) {
      return null;
    }

    const currentTimeMs = Date.now();
    let nextExpiration = null;

    if (settings.recurringPaymentsEnabled && payment.subscriptionExpirationDate) {
      nextExpiration = Math.max(payment.subscriptionExpirationDate, user.subscriptionUntil || 0, currentTimeMs);
    } else {
      const baseTime = user.subscriptionUntil && user.subscriptionUntil > currentTimeMs
        ? user.subscriptionUntil
        : currentTimeMs;
      nextExpiration = addDays(baseTime, settings.subscriptionDurationDays);
    }

    user.subscriptionUntil = nextExpiration;
    user.lastWarningAt = null;
    user.lastAccessGrantedAt = currentTimeMs;
    user.updatedAt = nowIso();
    this.save();
    return structuredClone(user);
  }

  grantSubscriptionDays(userId, days, reason = "admin_grant") {
    const user = this.state.users[String(userId)];
    if (!user) {
      return null;
    }

    const currentTimeMs = Date.now();
    const baseTime = user.subscriptionUntil && user.subscriptionUntil > currentTimeMs
      ? user.subscriptionUntil
      : currentTimeMs;

    user.subscriptionUntil = addDays(baseTime, days);
    user.lastWarningAt = null;
    user.lastAccessGrantedAt = currentTimeMs;
    user.updatedAt = nowIso();
    this.save();

    this.addAuditLog({
      type: "grant_subscription",
      userId: user.id,
      days,
      reason
    });

    return structuredClone(user);
  }

  revokeSubscription(userId, reason = "admin_revoke") {
    const user = this.state.users[String(userId)];
    if (!user) {
      return null;
    }

    user.subscriptionUntil = Date.now() - 1;
    user.updatedAt = nowIso();
    this.save();

    this.addAuditLog({
      type: "revoke_subscription",
      userId: user.id,
      reason
    });

    return structuredClone(user);
  }

  adjustBalance(userId, amount, reason = "admin_balance") {
    const user = this.state.users[String(userId)];
    if (!user) {
      return null;
    }

    user.balanceStars = Math.max(0, user.balanceStars + amount);
    user.updatedAt = nowIso();
    this.save();

    this.addAuditLog({
      type: "balance_adjustment",
      userId: user.id,
      amount,
      reason
    });

    return structuredClone(user);
  }

  purchaseWithBalance(userId, settings) {
    const user = this.state.users[String(userId)];
    if (!user) {
      return { ok: false, reason: "user_not_found" };
    }

    if (user.balanceStars < settings.subscriptionPriceStars) {
      return { ok: false, reason: "not_enough_balance" };
    }

    user.balanceStars -= settings.subscriptionPriceStars;
    this.save();
    const updatedUser = this.grantSubscriptionDays(userId, settings.subscriptionDurationDays, "balance_purchase");
    return { ok: true, user: updatedUser };
  }

  markWarningSent(userId) {
    const user = this.state.users[String(userId)];
    if (!user) {
      return null;
    }

    user.lastWarningAt = Date.now();
    user.updatedAt = nowIso();
    this.save();
    return structuredClone(user);
  }

  markAccessRevoked(userId) {
    const user = this.state.users[String(userId)];
    if (!user) {
      return null;
    }

    user.lastAccessRevokedAt = Date.now();
    user.updatedAt = nowIso();
    this.save();
    return structuredClone(user);
  }

  getDashboardStats(currentTimeMs = Date.now()) {
    const users = Object.values(this.state.users);
    const activeUsers = users.filter((user) => user.subscriptionUntil && user.subscriptionUntil > currentTimeMs);
    const expiredUsers = users.filter((user) => user.subscriptionUntil && user.subscriptionUntil <= currentTimeMs);
    const expiringSoonUsers = users.filter((user) => {
      if (!user.subscriptionUntil || user.subscriptionUntil <= currentTimeMs) {
        return false;
      }

      const warningThreshold = currentTimeMs + this.state.settings.warningDays * 24 * 60 * 60 * 1000;
      return user.subscriptionUntil <= warningThreshold;
    });

    const revenueStars = Object.values(this.state.payments).reduce((sum, payment) => sum + payment.totalAmount, 0);
    const totalBalanceStars = users.reduce((sum, user) => sum + (user.balanceStars || 0), 0);
    const channelMembers = users.filter((user) => user.channelMemberStatus === "member").length;

    return {
      totalUsers: users.length,
      activeSubscriptions: activeUsers.length,
      expiredSubscriptions: expiredUsers.length,
      expiringSoon: expiringSoonUsers.length,
      revenueStars,
      totalBalanceStars,
      channelMembers
    };
  }
}

function createStore(filePath) {
  return new JsonStore(filePath);
}

module.exports = {
  createStore
};

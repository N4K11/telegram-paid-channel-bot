const path = require("path");
const crypto = require("crypto");

function parseBoolean(value, fallback) {
  if (value === undefined || value === null || value === "") {
    return fallback;
  }

  const normalized = String(value).trim().toLowerCase();
  return ["1", "true", "yes", "on"].includes(normalized);
}

function parseNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function getConfig() {
  const port = parseNumber(process.env.PORT, 3000);

  return {
    botToken: process.env.TELEGRAM_BOT_TOKEN || "",
    channelId: process.env.TELEGRAM_CHANNEL_ID || "",
    adminUsername: process.env.ADMIN_USERNAME || "admin",
    adminPassword: process.env.ADMIN_PASSWORD || "",
    appTimezone: process.env.APP_TIMEZONE || "Europe/Saratov",
    baseUrl: process.env.BASE_URL || `http://localhost:${port}`,
    port,
    autoCreateInviteLink: parseBoolean(process.env.AUTO_CREATE_INVITE_LINK, true),
    channelInviteLink: process.env.CHANNEL_INVITE_LINK || "",
    pollTimeoutSeconds: parseNumber(process.env.POLL_TIMEOUT_SECONDS, 25),
    serviceCheckIntervalMs: parseNumber(process.env.SERVICE_CHECK_INTERVAL_MS, 60_000),
    dataFilePath: path.join(process.cwd(), "data", "db.json"),
    sessionSecret: process.env.SESSION_SECRET || crypto.randomBytes(32).toString("hex")
  };
}

function validateConfig(config) {
  const missing = [];

  if (!config.botToken) {
    missing.push("TELEGRAM_BOT_TOKEN");
  }

  if (!config.channelId) {
    missing.push("TELEGRAM_CHANNEL_ID");
  }

  if (!config.adminPassword) {
    missing.push("ADMIN_PASSWORD");
  }

  if (missing.length > 0) {
    const error = new Error(`Missing required environment variables: ${missing.join(", ")}`);
    error.code = "CONFIG_VALIDATION_FAILED";
    throw error;
  }
}

module.exports = {
  getConfig,
  validateConfig
};

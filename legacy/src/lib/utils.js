const crypto = require("crypto");

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function nowIso() {
  return new Date().toISOString();
}

function addDays(timestampMs, days) {
  return timestampMs + days * 24 * 60 * 60 * 1000;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatDateTime(timestampMs, timeZone) {
  if (!timestampMs) {
    return "—";
  }

  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone
  }).format(new Date(timestampMs));
}

function formatRelativeDuration(targetMs, nowMs = Date.now()) {
  if (!targetMs) {
    return "—";
  }

  const diff = targetMs - nowMs;
  const abs = Math.abs(diff);
  const dayMs = 24 * 60 * 60 * 1000;
  const hourMs = 60 * 60 * 1000;

  if (abs >= dayMs) {
    const days = Math.round(abs / dayMs);
    return diff >= 0 ? `через ${days} дн.` : `${days} дн. назад`;
  }

  const hours = Math.max(1, Math.round(abs / hourMs));
  return diff >= 0 ? `через ${hours} ч.` : `${hours} ч. назад`;
}

function formatUserName(user) {
  if (!user) {
    return "Пользователь";
  }

  const parts = [user.firstName, user.lastName].filter(Boolean);
  if (parts.length > 0) {
    return parts.join(" ");
  }

  if (user.username) {
    return `@${user.username}`;
  }

  return `ID ${user.id}`;
}

function createSignature(secret, value) {
  return crypto.createHmac("sha256", secret).update(value).digest("hex");
}

function parseCookies(header) {
  const cookies = {};
  if (!header) {
    return cookies;
  }

  for (const item of header.split(";")) {
    const trimmed = item.trim();
    if (!trimmed) {
      continue;
    }

    const separatorIndex = trimmed.indexOf("=");
    if (separatorIndex === -1) {
      continue;
    }

    const key = trimmed.slice(0, separatorIndex).trim();
    const value = trimmed.slice(separatorIndex + 1).trim();
    cookies[key] = decodeURIComponent(value);
  }

  return cookies;
}

function parseInteger(value, fallback = 0) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function parseBooleanFromForm(value) {
  return value === "on" || value === "true" || value === "1";
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];

    req.on("data", (chunk) => {
      chunks.push(chunk);
    });

    req.on("end", () => {
      resolve(Buffer.concat(chunks).toString("utf8"));
    });

    req.on("error", reject);
  });
}

function parseFormEncoded(body) {
  const params = new URLSearchParams(body);
  const result = {};

  for (const [key, value] of params.entries()) {
    result[key] = value;
  }

  return result;
}

function toJsonResponse(res, statusCode, payload) {
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8"
  });
  res.end(JSON.stringify(payload, null, 2));
}

module.exports = {
  addDays,
  createSignature,
  escapeHtml,
  formatDateTime,
  formatRelativeDuration,
  formatUserName,
  nowIso,
  parseBooleanFromForm,
  parseCookies,
  parseFormEncoded,
  parseInteger,
  readBody,
  sleep,
  toJsonResponse
};

class TelegramClient {
  constructor(botToken) {
    this.botToken = botToken;
    this.baseUrl = `https://api.telegram.org/bot${botToken}`;
  }

  async call(method, payload = {}) {
    const response = await fetch(`${this.baseUrl}/${method}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const body = await response.json();

    if (!body.ok) {
      const error = new Error(body.description || `Telegram API error at ${method}`);
      error.method = method;
      error.payload = payload;
      error.response = body;
      throw error;
    }

    return body.result;
  }

  getMe() {
    return this.call("getMe");
  }

  deleteWebhook(dropPendingUpdates = false) {
    return this.call("deleteWebhook", {
      drop_pending_updates: dropPendingUpdates
    });
  }

  getUpdates(offset, timeoutSeconds, allowedUpdates) {
    return this.call("getUpdates", {
      offset,
      timeout: timeoutSeconds,
      allowed_updates: allowedUpdates
    });
  }

  sendMessage(chatId, text, extra = {}) {
    return this.call("sendMessage", {
      chat_id: chatId,
      text,
      parse_mode: "HTML",
      ...extra
    });
  }

  answerCallbackQuery(callbackQueryId, text) {
    return this.call("answerCallbackQuery", {
      callback_query_id: callbackQueryId,
      text
    });
  }

  answerPreCheckoutQuery(preCheckoutQueryId, ok, errorMessage = "") {
    return this.call("answerPreCheckoutQuery", {
      pre_checkout_query_id: preCheckoutQueryId,
      ok,
      error_message: ok ? undefined : errorMessage
    });
  }

  sendInvoice(params) {
    return this.call("sendInvoice", params);
  }

  createChatInviteLink(chatId, name, createsJoinRequest = true) {
    return this.call("createChatInviteLink", {
      chat_id: chatId,
      name,
      creates_join_request: createsJoinRequest
    });
  }

  approveChatJoinRequest(chatId, userId) {
    return this.call("approveChatJoinRequest", {
      chat_id: chatId,
      user_id: userId
    });
  }

  declineChatJoinRequest(chatId, userId) {
    return this.call("declineChatJoinRequest", {
      chat_id: chatId,
      user_id: userId
    });
  }

  banChatMember(chatId, userId) {
    return this.call("banChatMember", {
      chat_id: chatId,
      user_id: userId,
      revoke_messages: false
    });
  }

  unbanChatMember(chatId, userId) {
    return this.call("unbanChatMember", {
      chat_id: chatId,
      user_id: userId
    });
  }
}

module.exports = {
  TelegramClient
};

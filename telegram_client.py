import json
import time
import urllib.error
import urllib.request


class TelegramClient:
    def __init__(
        self,
        bot_token,
        api_base_url="https://api.telegram.org",
        transport=None,
        sleep_fn=None,
        request_factory=None,
        timeout_seconds=30,
    ):
        self.bot_token = bot_token
        self.base_url = api_base_url.rstrip("/")
        self.transport = transport or urllib.request.urlopen
        self.sleep_fn = sleep_fn or time.sleep
        self.request_factory = request_factory or urllib.request.Request
        self.timeout_seconds = timeout_seconds

    def _build_url(self, method_name):
        return f"{self.base_url}/bot{self.bot_token}/{method_name}"

    def _build_request(self, method_name, payload):
        data = json.dumps(payload or {}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        return self.request_factory(
            self._build_url(method_name),
            data=data,
            headers=headers,
            method="POST",
        )

    @staticmethod
    def _parse_json_body(raw_body, method_name):
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Telegram API invalid JSON at {method_name}: {error}") from error

    @staticmethod
    def _read_response_body(response, method_name):
        try:
            return response.read().decode("utf-8")
        except UnicodeDecodeError as error:
            raise RuntimeError(f"Telegram API invalid encoding at {method_name}: {error}") from error

    def _parse_ok_response(self, method_name, raw_body):
        body = self._parse_json_body(raw_body, method_name)
        if not body.get("ok"):
            description = body.get("description") or f"Telegram API error at {method_name}"
            raise RuntimeError(f"Telegram API error at {method_name}: {description}")
        return body.get("result")

    def _parse_http_error(self, method_name, error):
        try:
            raw_body = error.read().decode("utf-8")
        except UnicodeDecodeError:
            raw_body = ""

        if raw_body:
            try:
                body = self._parse_json_body(raw_body, method_name)
                description = body.get("description") or str(error)
                return RuntimeError(f"Telegram API error at {method_name}: {description}")
            except RuntimeError:
                pass
        return RuntimeError(f"Telegram API error at {method_name}: {error}")

    def _is_terminal_error(self, error):
        if not isinstance(error, RuntimeError):
            return False
        message = str(error)
        return (
            "Telegram API error at" in message
            or "Telegram API invalid JSON at" in message
            or "Telegram API invalid encoding at" in message
        )

    def _request(self, method_name, payload=None, timeout=None):
        request = self._build_request(method_name, payload or {})
        timeout = timeout or self.timeout_seconds

        retries = 3
        for attempt in range(retries):
            try:
                with self.transport(request, timeout=timeout) as response:
                    raw_body = self._read_response_body(response, method_name)
                return self._parse_ok_response(method_name, raw_body)
            except urllib.error.HTTPError as error:
                raise self._parse_http_error(method_name, error) from error
            except Exception as error:
                if self._is_terminal_error(error):
                    raise
                if attempt < retries - 1:
                    self.sleep_fn(2 * (attempt + 1))
                    continue
                raise RuntimeError(f"Telegram API network error at {method_name}: {error}") from error

    def call(self, method, payload=None):
        return self._request(method, payload)

    def get_me(self):
        return self.call("getMe")

    def delete_webhook(self, drop_pending_updates=False):
        return self.call("deleteWebhook", {"drop_pending_updates": drop_pending_updates})

    def get_updates(self, offset, timeout_seconds, allowed_updates):
        return self.call(
            "getUpdates",
            {
                "offset": offset,
                "timeout": timeout_seconds,
                "allowed_updates": allowed_updates,
            },
        )

    def delete_message(self, chat_id, message_id):
        return self.call(
            "deleteMessage",
            {
                "chat_id": chat_id,
                "message_id": message_id,
            },
        )

    def send_message(self, chat_id, text, extra=None):
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if extra:
            payload.update(extra)
        return self.call("sendMessage", payload)

    def edit_message_text(self, chat_id, message_id, text, extra=None):
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if extra:
            payload.update(extra)
        try:
            return self.call("editMessageText", payload)
        except RuntimeError as error:
            if "message is not modified" in str(error).lower():
                return None
            raise

    def answer_callback_query(self, callback_query_id, text="", show_alert=False):
        return self.call(
            "answerCallbackQuery",
            {
                "callback_query_id": callback_query_id,
                "text": text,
                "show_alert": show_alert,
            },
        )

    def answer_pre_checkout_query(self, pre_checkout_query_id, ok, error_message=""):
        payload = {
            "pre_checkout_query_id": pre_checkout_query_id,
            "ok": ok,
        }
        if not ok:
            payload["error_message"] = error_message
        return self.call("answerPreCheckoutQuery", payload)

    def send_invoice(self, params):
        return self.call("sendInvoice", params)

    def create_chat_invite_link(self, chat_id, name, creates_join_request=True):
        return self.call(
            "createChatInviteLink",
            {
                "chat_id": chat_id,
                "name": name,
                "creates_join_request": creates_join_request,
            },
        )

    def get_chat_member(self, chat_id, user_id):
        return self.call(
            "getChatMember",
            {
                "chat_id": chat_id,
                "user_id": user_id,
            },
        )

    def approve_chat_join_request(self, chat_id, user_id):
        return self.call(
            "approveChatJoinRequest",
            {
                "chat_id": chat_id,
                "user_id": user_id,
            },
        )

    def decline_chat_join_request(self, chat_id, user_id):
        return self.call(
            "declineChatJoinRequest",
            {
                "chat_id": chat_id,
                "user_id": user_id,
            },
        )

    def ban_chat_member(self, chat_id, user_id):
        return self.call(
            "banChatMember",
            {
                "chat_id": chat_id,
                "user_id": user_id,
                "revoke_messages": False,
            },
        )

    def unban_chat_member(self, chat_id, user_id):
        return self.call(
            "unbanChatMember",
            {
                "chat_id": chat_id,
                "user_id": user_id,
            },
        )

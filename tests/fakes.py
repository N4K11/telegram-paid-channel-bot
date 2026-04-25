class FakeTelegramClient:
    def __init__(self, updates_batches=None, failures=None):
        self.updates_batches = list(updates_batches or [])
        self.failures = failures or {}
        self.calls = []
        self.next_message_id = 1

    def _record(self, method, **payload):
        entry = {"method": method, **payload}
        self.calls.append(entry)
        return entry

    def _maybe_fail(self, method, *args, **kwargs):
        failure = self.failures.get(method)
        if failure is None:
            return
        if callable(failure):
            failure(*args, **kwargs)
            return
        raise failure

    def get_calls(self, method):
        return [call for call in self.calls if call["method"] == method]

    def get_me(self):
        self._record("get_me")
        self._maybe_fail("get_me")
        return {"id": 1, "username": "fake_bot"}

    def delete_webhook(self, drop_pending_updates=False):
        self._record("delete_webhook", drop_pending_updates=drop_pending_updates)
        self._maybe_fail("delete_webhook", drop_pending_updates)
        return True

    def get_updates(self, offset, timeout_seconds, allowed_updates):
        self._record(
            "get_updates",
            offset=offset,
            timeout_seconds=timeout_seconds,
            allowed_updates=list(allowed_updates or []),
        )
        self._maybe_fail("get_updates", offset, timeout_seconds, allowed_updates)
        if self.updates_batches:
            return self.updates_batches.pop(0)
        return []

    def delete_message(self, chat_id, message_id):
        self._record("delete_message", chat_id=chat_id, message_id=message_id)
        self._maybe_fail("delete_message", chat_id, message_id)
        return True

    def send_message(self, chat_id, text, extra=None):
        self._record("send_message", chat_id=chat_id, text=text, extra=extra)
        self._maybe_fail("send_message", chat_id, text, extra)
        message = {"message_id": self.next_message_id}
        self.next_message_id += 1
        return message

    def edit_message_text(self, chat_id, message_id, text, extra=None):
        self._record(
            "edit_message_text",
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            extra=extra,
        )
        self._maybe_fail("edit_message_text", chat_id, message_id, text, extra)
        return True

    def answer_callback_query(self, callback_query_id, text=""):
        self._record("answer_callback_query", callback_query_id=callback_query_id, text=text)
        self._maybe_fail("answer_callback_query", callback_query_id, text)
        return True

    def answer_pre_checkout_query(self, pre_checkout_query_id, ok, error_message=""):
        self._record(
            "answer_pre_checkout_query",
            pre_checkout_query_id=pre_checkout_query_id,
            ok=ok,
            error_message=error_message,
        )
        self._maybe_fail("answer_pre_checkout_query", pre_checkout_query_id, ok, error_message)
        return True

    def send_invoice(self, params):
        self._record("send_invoice", params=params)
        self._maybe_fail("send_invoice", params)
        return {"message_id": self.next_message_id}

    def create_chat_invite_link(self, chat_id, name, creates_join_request=True):
        self._record(
            "create_chat_invite_link",
            chat_id=chat_id,
            name=name,
            creates_join_request=creates_join_request,
        )
        self._maybe_fail("create_chat_invite_link", chat_id, name, creates_join_request)
        return {"invite_link": "https://t.me/+fake_invite"}

    def approve_chat_join_request(self, chat_id, user_id):
        self._record("approve_chat_join_request", chat_id=chat_id, user_id=user_id)
        self._maybe_fail("approve_chat_join_request", chat_id, user_id)
        return True

    def decline_chat_join_request(self, chat_id, user_id):
        self._record("decline_chat_join_request", chat_id=chat_id, user_id=user_id)
        self._maybe_fail("decline_chat_join_request", chat_id, user_id)
        return True

    def ban_chat_member(self, chat_id, user_id):
        self._record("ban_chat_member", chat_id=chat_id, user_id=user_id)
        self._maybe_fail("ban_chat_member", chat_id, user_id)
        return True

    def unban_chat_member(self, chat_id, user_id):
        self._record("unban_chat_member", chat_id=chat_id, user_id=user_id)
        self._maybe_fail("unban_chat_member", chat_id, user_id)
        return True
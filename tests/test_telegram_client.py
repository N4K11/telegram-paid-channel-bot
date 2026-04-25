import io
import json
import unittest
import urllib.error

from telegram_client import TelegramClient


class FakeHttpResponse:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeHttpTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, request, timeout=30):
        self.calls.append(
            {
                "url": request.full_url,
                "method": request.get_method(),
                "payload": json.loads((request.data or b"{}").decode("utf-8")),
                "timeout": timeout,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return FakeHttpResponse(response)


def ok_response(result):
    return json.dumps({"ok": True, "result": result}).encode("utf-8")


def error_response(description):
    return json.dumps({"ok": False, "description": description}).encode("utf-8")


def http_error(status, description):
    payload = error_response(description)
    return urllib.error.HTTPError(
        url="https://api.telegram.org/botTOKEN/test",
        code=status,
        msg="HTTP error",
        hdrs=None,
        fp=io.BytesIO(payload),
    )


class TelegramClientTransportTests(unittest.TestCase):
    def make_client(self, responses):
        transport = FakeHttpTransport(responses)
        client = TelegramClient(
            "TOKEN",
            transport=transport,
            sleep_fn=lambda _: None,
        )
        return client, transport

    def test_get_me_success(self):
        client, transport = self.make_client([ok_response({"id": 1, "username": "bot"})])

        result = client.get_me()

        self.assertEqual(result, {"id": 1, "username": "bot"})
        self.assertTrue(transport.calls[0]["url"].endswith("/getMe"))
        self.assertEqual(transport.calls[0]["method"], "POST")
        self.assertEqual(transport.calls[0]["payload"], {})

    def test_send_message_payload(self):
        client, transport = self.make_client([ok_response({"message_id": 1})])

        client.send_message(123, "hello", {"reply_markup": {"inline_keyboard": []}})

        payload = transport.calls[0]["payload"]
        self.assertTrue(transport.calls[0]["url"].endswith("/sendMessage"))
        self.assertEqual(payload["chat_id"], 123)
        self.assertEqual(payload["text"], "hello")
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertIn("reply_markup", payload)

    def test_edit_message_not_modified_is_safe(self):
        client, transport = self.make_client([http_error(400, "Bad Request: message is not modified")])

        result = client.edit_message_text(123, 10, "hello")

        self.assertIsNone(result)
        self.assertTrue(transport.calls[0]["url"].endswith("/editMessageText"))

    def test_edit_message_other_error_is_reported(self):
        client, _ = self.make_client([http_error(400, "Bad Request: message to edit not found")])

        with self.assertRaises(RuntimeError) as error:
            client.edit_message_text(123, 10, "hello")

        self.assertIn("Telegram API error at editMessageText", str(error.exception))

    def test_send_invoice_stars_payload(self):
        client, transport = self.make_client([ok_response({"message_id": 2})])
        params = {
            "chat_id": 123,
            "title": "Title",
            "description": "Description",
            "payload": "subscription:123",
            "currency": "XTR",
            "prices": [{"label": "Access", "amount": 250}],
        }

        client.send_invoice(params)

        payload = transport.calls[0]["payload"]
        self.assertTrue(transport.calls[0]["url"].endswith("/sendInvoice"))
        self.assertEqual(payload["currency"], "XTR")
        self.assertEqual(payload["payload"], "subscription:123")
        self.assertEqual(payload["prices"][0]["amount"], 250)

    def test_join_request_methods_payload(self):
        client, transport = self.make_client([ok_response(True), ok_response(True)])

        client.approve_chat_join_request("@channel", 123)
        client.decline_chat_join_request("@channel", 123)

        approve_payload = transport.calls[0]["payload"]
        decline_payload = transport.calls[1]["payload"]
        self.assertTrue(transport.calls[0]["url"].endswith("/approveChatJoinRequest"))
        self.assertTrue(transport.calls[1]["url"].endswith("/declineChatJoinRequest"))
        self.assertEqual(approve_payload, {"chat_id": "@channel", "user_id": 123})
        self.assertEqual(decline_payload, {"chat_id": "@channel", "user_id": 123})

    def test_ban_unban_payload(self):
        client, transport = self.make_client([ok_response(True), ok_response(True)])

        client.ban_chat_member("@channel", 123)
        client.unban_chat_member("@channel", 123)

        ban_payload = transport.calls[0]["payload"]
        unban_payload = transport.calls[1]["payload"]
        self.assertTrue(transport.calls[0]["url"].endswith("/banChatMember"))
        self.assertTrue(transport.calls[1]["url"].endswith("/unbanChatMember"))
        self.assertEqual(ban_payload, {"chat_id": "@channel", "user_id": 123, "revoke_messages": False})
        self.assertEqual(unban_payload, {"chat_id": "@channel", "user_id": 123})

    def test_get_updates_payload(self):
        client, transport = self.make_client([ok_response([])])

        client.get_updates(5, 25, ["message", "callback_query"])

        payload = transport.calls[0]["payload"]
        self.assertTrue(transport.calls[0]["url"].endswith("/getUpdates"))
        self.assertEqual(payload["offset"], 5)
        self.assertEqual(payload["timeout"], 25)
        self.assertEqual(payload["allowed_updates"], ["message", "callback_query"])

    def test_network_error_handled_predictably(self):
        client, _ = self.make_client([OSError("network down"), OSError("network down"), OSError("network down")])

        with self.assertRaises(RuntimeError) as error:
            client.get_me()

        self.assertIn("Telegram API network error at getMe", str(error.exception))

    def test_invalid_json_handled_predictably(self):
        client, _ = self.make_client([b"not-json"])

        with self.assertRaises(RuntimeError) as error:
            client.get_me()

        self.assertIn("Telegram API invalid JSON at getMe", str(error.exception))


if __name__ == "__main__":
    unittest.main()
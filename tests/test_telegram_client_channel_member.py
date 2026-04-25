import json
import unittest

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
        return FakeHttpResponse(self.responses.pop(0))


def ok_response(result):
    return json.dumps({"ok": True, "result": result}).encode("utf-8")


class TelegramClientChannelMemberTests(unittest.TestCase):
    def test_get_chat_member_payload(self):
        transport = FakeHttpTransport([ok_response({"status": "administrator"})])
        client = TelegramClient("TOKEN", transport=transport, sleep_fn=lambda _: None)

        result = client.get_chat_member("@channel", 123)

        self.assertEqual(result, {"status": "administrator"})
        self.assertTrue(transport.calls[0]["url"].endswith("/getChatMember"))
        self.assertEqual(transport.calls[0]["method"], "POST")
        self.assertEqual(transport.calls[0]["payload"], {"chat_id": "@channel", "user_id": 123})


if __name__ == "__main__":
    unittest.main()

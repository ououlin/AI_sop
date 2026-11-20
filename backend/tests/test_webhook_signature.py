# -*- coding: utf-8 -*-
"""Webhook 签名与重试补充测试。"""

import hashlib
import hmac

from tests.test_openplatform import OpenPlatformBase
from openplatform.webhook_manager import WebhookManager
import unittest


class WebhookSignatureTests(OpenPlatformBase):
    def setUp(self):
        super().setUp()
        self.manager = WebhookManager(max_attempts=3, retry_backoff=0)

    def test_signature_matches_manual_hmac(self):
        secret = "s3cret"
        body = b'{"event":"execution.completed","data":{"record_id":1}}'
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        self.assertEqual(self.manager._sign(secret, body), expected)

    def test_retry_then_success(self):
        calls = []

        def fake_send(url, secret, body, event):
            calls.append(1)
            if len(calls) >= 2:
                return True, "HTTP 200"
            return False, "HTTP 500"

        self.manager._send_once = fake_send
        self.manager._deliver_with_retry(
            "https://example.com/hook", "s3cret", "execution.completed", b"{}"
        )

        delivery = self.manager.recent_deliveries()[0]
        self.assertEqual(delivery["status"], "ok")
        self.assertEqual(delivery["attempts"], 2)
        self.assertEqual(len(calls), 2)

    def test_all_attempts_fail(self):
        self.manager._send_once = lambda *args, **kwargs: (False, "HTTP 503")
        self.manager._deliver_with_retry(
            "https://example.com/hook", "", "execution.failed", b"{}"
        )

        delivery = self.manager.recent_deliveries()[0]
        self.assertEqual(delivery["status"], "failed")
        self.assertEqual(delivery["attempts"], 3)
        self.assertEqual(delivery["detail"], "HTTP 503")

    def test_first_attempt_success(self):
        self.manager._send_once = lambda *args, **kwargs: (True, "HTTP 204")
        self.manager._deliver_with_retry(
            "https://example.com/hook", "", "execution.started", b"{}"
        )
        self.assertEqual(self.manager.recent_deliveries()[0]["attempts"], 1)


if __name__ == "__main__":
    unittest.main()

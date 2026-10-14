import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

from performance_client import PerformanceClient, PerformanceError


class PerformanceClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = PerformanceClient(Path(self.temp.name))

    def test_settings_keep_token_private_and_clear_on_host_change(self):
        result = self.client.save({"baseUrl":"http://192.168.100.247:8765", "token":"secret-test"})
        self.assertTrue(result["configured"])
        self.assertNotIn("secret-test", json.dumps(result))
        self.assertEqual(self.client.path.stat().st_mode & 0o777, 0o600)
        self.client.save({"baseUrl":"http://localhost:8000"})
        self.assertFalse(self.client.settings()["configured"])

    def test_proxy_only_forwards_read_routes_and_known_filters(self):
        self.client.save({"token":"secret-test"})
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = io.BytesIO(b'{"ok":true,"data":{"items":[]}}')
        with patch("performance_client.urllib.request.build_opener",return_value=opener):
            self.client.get("records","department=test&due_from=2026-10-08&page=2&token=bad")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(),"GET")
        self.assertIn("due_from=2026-10-08",request.full_url)
        self.assertNotIn("token=",request.full_url)
        self.assertEqual(request.get_header("Authorization"),"Bearer secret-test")
        with self.assertRaises(PerformanceError):
            self.client.get("../healthz")

    def test_authentication_and_upstream_errors_preserve_status_without_secret(self):
        with self.assertRaises(PerformanceError) as context:
            self.client.get("meta")
        self.assertEqual(context.exception.status,401)
        self.client.save({"token":"secret-test"})
        error = urllib.error.HTTPError("http://example",403,"Forbidden",{},io.BytesIO(b'{"detail":"secret-test forbidden"}'))
        with patch("performance_client.urllib.request.build_opener") as factory:
            factory.return_value.open.side_effect = error
            with self.assertRaises(PerformanceError) as context:
                self.client.get("meta")
        self.assertEqual(context.exception.status,403)
        self.assertNotIn("secret-test",str(context.exception))

    def test_invalid_url_and_token_rejected(self):
        for url in ("file:///tmp/key","http://user:pass@localhost","http://localhost/v1"):
            with self.assertRaises(PerformanceError): self.client.save({"baseUrl":url})
        with self.assertRaises(PerformanceError): self.client.save({"token":"bad\nheader"})

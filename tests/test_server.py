"""The HTTP adapter must always answer, even when the application blows up."""
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mailweb.web.http import Response  # noqa: E402
from mailweb.web.server import WebServer  # noqa: E402


class Exploding:
    def handle(self, request):
        if request.path == "/boom":
            raise RuntimeError("bug in the application")
        return Response(200, b"fine", {"Content-Type": "text/plain"})


class Adapter(unittest.TestCase):
    def test_unexpected_error_still_gets_a_json_500(self):
        server = WebServer(Exploding(), "127.0.0.1", 0)
        port = server.httpd.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/boom", timeout=5)
            self.assertEqual(ctx.exception.code, 500)
            self.assertEqual(json.load(ctx.exception)["error"], "internal server error")
            self.assertEqual(urllib.request.urlopen(f"http://127.0.0.1:{port}/ok", timeout=5).read(), b"fine")
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()

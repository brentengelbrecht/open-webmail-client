"""HTTPS: the handshake must not be able to block other connections; http:// gets a redirect; bad files are explained."""
import http.client
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mailweb.config import ConfigError  # noqa: E402
from mailweb.web.http import Response  # noqa: E402
from mailweb.web.server import WebServer  # noqa: E402


class Hello:
    def handle(self, request):
        return Response(200, b"hello", {"Content-Type": "text/plain"})


def make_cert(directory: Path, name: str, passphrase: str = ""):
    cert, key = directory / f"{name}.crt", directory / f"{name}.key"
    cmd = ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-days", "2", "-subj", "/CN=localhost",
           "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1", "-keyout", str(key), "-out", str(cert)]
    cmd += ["-passout", f"pass:{passphrase}"] if passphrase else ["-nodes"]
    subprocess.run(cmd, check=True, capture_output=True)
    return str(cert), str(key)


@unittest.skipUnless(shutil.which("openssl"), "openssl is needed to make test certificates")
class Tls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.cert, cls.key = make_cert(cls.dir, "good")
        cls.server = WebServer(Hello(), "127.0.0.1", 0, cls.cert, cls.key)
        cls.port = cls.server.httpd.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.tmp.cleanup()

    def get(self):
        context = ssl.create_default_context(cafile=self.cert)
        return urllib.request.urlopen(f"https://localhost:{self.port}/", context=context, timeout=5).read()

    def test_https_works_when_the_certificate_is_trusted(self):
        self.assertTrue(self.server.tls)
        self.assertEqual(self.get(), b"hello")

    def test_a_silent_connection_does_not_block_everyone_else(self):
        idle = socket.create_connection(("127.0.0.1", self.port))       # like a browser's speculative pre-connection
        try:
            started = time.monotonic()
            self.assertEqual(self.get(), b"hello")
            self.assertLess(time.monotonic() - started, 3)
        finally:
            idle.close()

    def test_a_client_that_dies_mid_handshake_does_not_break_the_server(self):
        junk = socket.create_connection(("127.0.0.1", self.port))
        junk.sendall(b"\x16\x03\x01garbage")
        junk.close()
        self.assertEqual(self.get(), b"hello")

    def test_plain_http_on_the_https_port_is_redirected(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request("GET", "/some/page?x=1", headers={"Host": f"localhost:{self.port}"})
        response = connection.getresponse()
        self.assertEqual(response.status, 307)                          # temporary: never cached by the browser
        self.assertEqual(response.getheader("Location"), f"https://localhost:{self.port}/some/page?x=1")
        connection.close()

    def test_the_redirect_cannot_be_abused_with_a_crafted_host_header(self):
        for host in ("evil.example/steal", "user@evil.example", "evil.example\\@x"):
            with socket.create_connection(("127.0.0.1", self.port), timeout=5) as raw:
                raw.sendall(f"GET / HTTP/1.1\r\nHost: {host}\r\n\r\n".encode())
                reply = raw.recv(4096).decode("latin-1")
            self.assertTrue(reply.startswith("HTTP/1.1 400"), f"{host!r} -> {reply[:60]!r}")
            self.assertNotIn("Location:", reply)

    def test_bad_files_are_explained_not_dumped_as_tracebacks(self):
        other_cert, other_key = make_cert(self.dir, "other")
        with self.assertRaisesRegex(ConfigError, "not found"):
            WebServer(Hello(), "127.0.0.1", 0, str(self.dir / "missing.crt"), self.key)
        with self.assertRaisesRegex(ConfigError, "cannot use the TLS certificate"):
            WebServer(Hello(), "127.0.0.1", 0, self.cert, other_key)             # key does not match
        enc_cert, enc_key = make_cert(self.dir, "enc", passphrase="secret")
        with self.assertRaisesRegex(ConfigError, "passphrase"):                  # and it must not wait for terminal input
            WebServer(Hello(), "127.0.0.1", 0, enc_cert, enc_key)


if __name__ == "__main__":
    unittest.main()

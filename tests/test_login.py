"""Credentials with unusual characters must log in (they are sent as UTF-8 quoted strings)."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fake_repo  # noqa: E402
from harness import HangingImapServer, server_allows_spaces_in_logins, start_server  # noqa: E402
from mailweb.accounts import AccountRegistry, AccountStore  # noqa: E402
from mailweb.config import MailSettings  # noqa: E402
from mailweb.errors import UpstreamError  # noqa: E402
from mailweb.imap import ImapEndpoint, ImapGateway  # noqa: E402

CASES = [
    ("you@example.com", "secret"),
    ("first.last+tag@sub.example.co.uk", "pa$$w0rd!"),
    ("us er@example.com", "secret"),                 # space in the user name
    ("jos\u00e9@example.com", "p\u00e4ss w\u00f6rd"),    # non-ASCII user name and password
    ("DOMAIN\\you", "secret"),
]


class Login(unittest.TestCase):
    def test_unusual_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = fake_repo.build(Path(tmp))
            for user, password in CASES:
                with self.subTest(user=user):
                    if " " in user and not server_allows_spaces_in_logins():
                        continue                       # this server refuses such names; see the quoting test below
                    server, port = start_server(Path(tmp), repo, user, password)
                    registry = AccountRegistry(AccountStore(Path(tmp) / f"a{port}.json", "pw"), MailSettings())
                    try:
                        info = registry.add({"host": "127.0.0.1", "port": port, "user": user, "password": password})
                        self.assertEqual(registry.service(info.id).folders()[0].name, "INBOX")
                        with self.assertRaises(UpstreamError):
                            registry.add({"host": "127.0.0.1", "port": port, "user": user, "password": password + "x"})
                    finally:
                        registry.close()
                        server.terminate()
                        server.wait(5)

    def test_user_names_and_passwords_are_sent_as_quoted_utf8_strings(self):
        server = HangingImapServer()
        self.addCleanup(server.sock.close)
        gateway = ImapGateway(ImapEndpoint("127.0.0.1", server.port, "us er@example.com", 'p\u00e4ss "w"', timeout=5), size=1)
        self.addCleanup(gateway.close)
        gateway.run(lambda imap: None)                    # connecting is enough: it logs in
        self.assertEqual(server.logins, ['LOGIN "us er@example.com" "p\u00e4ss \\"w\\""'])

    def test_connection_refused_is_explained_and_not_retried(self):
        import time
        from harness import free_port
        with tempfile.TemporaryDirectory() as tmp:
            registry = AccountRegistry(AccountStore(Path(tmp) / "a.json", "pw"), MailSettings())
            port, started = free_port(), time.monotonic()
            with self.assertRaises(UpstreamError) as ctx:
                registry.add({"host": "127.0.0.1", "port": port, "user": "u", "password": "p"})
            self.assertIn(f"127.0.0.1:{port}", str(ctx.exception))
            self.assertIn("connection refused", str(ctx.exception))
            self.assertLess(time.monotonic() - started, 2)
            self.assertEqual(registry.list(), [])


if __name__ == "__main__":
    unittest.main()

"""A slow server is not a broken one: searches get their own timeout, nothing is retried on a timeout, and a
failure releases the connection at once."""
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from harness import HangingImapServer  # noqa: E402
from mailweb.errors import UpstreamError  # noqa: E402
from mailweb.imap import ImapEndpoint, ImapGateway  # noqa: E402


class Timeouts(unittest.TestCase):
    def gateway(self, server, timeout=1, search_timeout=6):
        gateway = ImapGateway(ImapEndpoint("127.0.0.1", server.port, "u", "p", timeout=timeout, search_timeout=search_timeout), size=2)
        self.addCleanup(gateway.close)
        self.addCleanup(server.sock.close)
        return gateway

    def test_a_slow_search_is_allowed_to_finish(self):
        server = HangingImapServer(search_delay=2.5)                 # slower than the normal 1 s timeout
        gateway = self.gateway(server)
        uids = gateway.run(lambda imap: (imap.select_folder("INBOX"), imap.uid_search([b"TEXT", b'"x"']))[1])
        self.assertEqual(uids, [1, 2, 3])
        self.assertEqual(server.search_requests, 1)

    def test_other_commands_still_use_the_short_timeout_and_are_not_retried(self):
        server = HangingImapServer()
        gateway = self.gateway(server)
        started = time.monotonic()
        with self.assertRaisesRegex(UpstreamError, "did not answer in time"):
            gateway.run(lambda imap: imap.list_folders())            # the server never answers LIST
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 2.5)                                # one 1 s timeout; before: 2 attempts plus a LOGOUT wait
        self.assertEqual(server.list_requests, 1)

    def test_a_search_that_exceeds_even_its_own_timeout_fails_once_with_advice(self):
        server = HangingImapServer(search_delay=5)
        gateway = self.gateway(server, timeout=1, search_timeout=2)
        started = time.monotonic()
        with self.assertRaisesRegex(UpstreamError, "narrower one"):
            gateway.run(lambda imap: (imap.select_folder("INBOX"), imap.uid_search([b"ALL"]))[1])
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual(server.search_requests, 1)                 # not repeated


if __name__ == "__main__":
    unittest.main()

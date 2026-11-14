import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mailweb.imap import ImapConnection, ImapEndpoint  # noqa: E402
from mailweb.imap.responses import parse_list  # noqa: E402

# What Gmail sends for LIST "" * (abridged), including a name that arrives as a literal.
GMAIL_LIST = [
    b'(\\HasNoChildren) "/" "INBOX"',
    b'(\\HasNoChildren) "/" "Receipts"',
    b'(\\Noselect \\HasChildren) "/" "[Gmail]"',
    b'(\\All \\HasNoChildren) "/" "[Gmail]/All Mail"',
    b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"',
    (b'(\\HasNoChildren) "/" {9}', b'Caf&AOk-s'),
]


class ListParsing(unittest.TestCase):
    def test_attributes_and_selectability(self):
        entries = {e.name: e for e in parse_list(GMAIL_LIST)}
        self.assertFalse(entries["[Gmail]"].selectable)
        self.assertTrue(entries["[Gmail]/All Mail"].selectable)
        self.assertIn("\\all", entries["[Gmail]/All Mail"].attributes)

    def test_literal_and_utf7_names(self):
        self.assertIn("Cafés", [e.name for e in parse_list(GMAIL_LIST)])

    def test_unselectable_parents_are_not_offered(self):
        class FakeClient:
            def list(self):
                return "OK", GMAIL_LIST
        conn = ImapConnection(ImapEndpoint("h", 993, "u", "p"))
        conn._client = FakeClient()
        names = conn.list_folders()
        self.assertNotIn("[Gmail]", names)
        self.assertEqual(names[:3], ["INBOX", "Receipts", "[Gmail]/All Mail"])


# ---- LIST-STATUS and the connection pool ---------------------------------------------------------
import threading  # noqa: E402
from unittest import mock  # noqa: E402

from mailweb.errors import UpstreamError  # noqa: E402
from mailweb.imap import ImapGateway  # noqa: E402
from mailweb.imap.responses import parse_status_lines  # noqa: E402

STATUS_LINES = [b'"INBOX" (MESSAGES 120 UNSEEN 4)', b'"[Gmail]/All Mail" (MESSAGES 9000 UNSEEN 0)',
                b'"Caf&AOk-s" (MESSAGES 2 UNSEEN 1)']


class ListStatus(unittest.TestCase):
    def test_parse_status_lines(self):
        counts = parse_status_lines(STATUS_LINES)
        self.assertEqual(counts["INBOX"], (120, 4))
        self.assertEqual(counts["[Gmail]/All Mail"], (9000, 0))
        self.assertEqual(counts["Cafés"], (2, 1))

    def _connection(self, caps, client):
        conn = ImapConnection(ImapEndpoint("h", 993, "u", "p"))
        conn._client, conn._caps = client, frozenset(caps)
        return conn

    def test_one_round_trip_when_the_server_has_list_status(self):
        class Client:
            commands = []

            def xatom(self, *args):
                self.commands.append(args)
                return "OK", [b"done"]

            def response(self, code):
                return code, {"LIST": GMAIL_LIST[:4], "STATUS": STATUS_LINES}[code]

            def status(self, *a):
                raise AssertionError("per-folder STATUS must not be used")

        conn = self._connection({"IMAP4REV1", "LIST-STATUS"}, Client())
        result = conn.list_folders_with_counts()
        self.assertEqual(result[0], ("INBOX", 120, 4))
        self.assertEqual(result[2], ("[Gmail]/All Mail", 9000, 0))      # unselectable "[Gmail]" is dropped
        self.assertEqual(len(Client.commands), 1)

    def test_falls_back_to_one_status_per_folder_and_tolerates_failures(self):
        class Client:
            def list(self):
                return "OK", GMAIL_LIST[:3]

            def status(self, name, items):
                return ("NO", [b"nope"]) if "Receipts" in name else ("OK", [b'"x" (MESSAGES 5 UNSEEN 2)'])

        result = self._connection({"IMAP4REV1"}, Client()).list_folders_with_counts()
        self.assertEqual(result, [("INBOX", 5, 2), ("Receipts", 0, 0)])


class Pool(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(ImapConnection, "ensure_connected", lambda self: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_slow_operations_do_not_block_each_other(self):
        gateway = ImapGateway(ImapEndpoint("h", 1, "u", "p"), size=2)
        meeting = threading.Barrier(2, timeout=3)          # both operations must be inside at the same time
        outcomes = []

        def op(conn):
            meeting.wait()
            return "ok"

        threads = [threading.Thread(target=lambda: outcomes.append(gateway.run(op))) for _ in range(2)]
        [t.start() for t in threads]
        [t.join(5) for t in threads]
        self.assertEqual(outcomes, ["ok", "ok"])

    def test_pool_is_capped_and_connections_are_reused(self):
        gateway = ImapGateway(ImapEndpoint("h", 1, "u", "p"), size=2)
        seen = set()
        for _ in range(6):
            gateway.run(lambda conn: seen.add(id(conn)))
        self.assertEqual(len(seen), 1)                     # sequential use keeps reusing one connection
        self.assertLessEqual(gateway._created, 2)

    def test_error_from_an_operation_returns_the_connection(self):
        gateway = ImapGateway(ImapEndpoint("h", 1, "u", "p"), size=1)

        def failing(conn):
            raise UpstreamError("boom")

        with self.assertRaises(UpstreamError):
            gateway.run(failing)
        self.assertEqual(gateway.run(lambda conn: "still works"), "still works")      # size 1: would hang if leaked


if __name__ == "__main__":
    unittest.main()

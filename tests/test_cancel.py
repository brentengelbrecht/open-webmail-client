"""cancel() must stop a running IMAP call at once (over a real socket) and never retry it."""
import socket
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mailweb.errors import Cancelled  # noqa: E402
from mailweb.imap import ImapEndpoint, ImapGateway  # noqa: E402


class HangingImapServer:
    """Greets, logs in, then goes silent when asked for LIST (like a very slow server)."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        self.list_requests = 0
        self.closed_by_client = threading.Event()
        self.got_list = threading.Event()
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        f = conn.makefile("rwb", buffering=0)
        f.write(b"* OK ready\r\n")
        while True:
            line = f.readline()
            if not line:
                self.closed_by_client.set()
                return
            tag, _, rest = line.decode().strip().partition(" ")
            command = rest.split(" ")[0].upper()
            if command == "CAPABILITY":
                f.write(b"* CAPABILITY IMAP4rev1\r\n" + f"{tag} OK done\r\n".encode())
            elif command == "LOGIN":
                f.write(f"{tag} OK logged in\r\n".encode())
            elif command == "LIST":
                self.list_requests += 1
                self.got_list.set()                      # ...and never answer
            elif command == "LOGOUT":
                f.write(f"{tag} OK bye\r\n".encode())
                return


class Cancel(unittest.TestCase):
    def setUp(self):
        self.server = HangingImapServer()
        self.addCleanup(self.server.sock.close)
        self.gateway = ImapGateway(ImapEndpoint("127.0.0.1", self.server.port, "u", "p", timeout=30), size=2)
        self.addCleanup(self.gateway.close)

    def _start(self, results):
        def work():
            try:
                results.append(self.gateway.run(lambda imap: imap.list_folders()))
            except Exception as exc:                       # noqa: BLE001
                results.append(exc)
        thread = threading.Thread(target=work)
        thread.start()
        return thread

    def test_running_call_is_interrupted_immediately_and_not_retried(self):
        results = []
        thread = self._start(results)
        self.assertTrue(self.server.got_list.wait(5), "the server never saw LIST")
        started = time.monotonic()
        self.gateway.cancel()
        thread.join(3)
        self.assertFalse(thread.is_alive(), "the call kept running after cancel()")
        self.assertLess(time.monotonic() - started, 2)       # nowhere near the 30 s socket timeout
        self.assertIsInstance(results[0], Cancelled)
        self.assertEqual(self.server.list_requests, 1)       # not retried on a fresh connection
        self.assertTrue(self.server.closed_by_client.wait(2))

    def test_queued_calls_never_start_and_later_calls_work(self):
        gateway = ImapGateway(ImapEndpoint("127.0.0.1", self.server.port, "u", "p", timeout=30), size=1)
        self.addCleanup(gateway.close)
        results = []

        def work():
            try:
                results.append(gateway.run(lambda imap: imap.list_folders()))
            except Exception as exc:                       # noqa: BLE001
                results.append(exc)
        first, second = threading.Thread(target=work), threading.Thread(target=work)
        first.start()
        self.assertTrue(self.server.got_list.wait(5))
        second.start()                                       # waits for the only connection
        time.sleep(0.2)
        gateway.cancel()
        first.join(3)
        second.join(3)
        self.assertEqual([type(r) for r in results], [Cancelled, Cancelled])
        self.assertEqual(self.server.list_requests, 1)       # the queued call never reached the server
        self.assertEqual(gateway.run(lambda imap: "usable again"), "usable again")


if __name__ == "__main__":
    unittest.main()

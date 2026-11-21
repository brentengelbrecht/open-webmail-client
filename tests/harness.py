"""Starts the real imap_archive_server.py on a synthetic repository (shared by tests)."""
import importlib.util
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_server_script():
    for candidate in (os.environ.get("IMAP_SERVER_PY"), ROOT.parent / "imap_archive_server.py",
                      "/mnt/user-data/uploads/imap_archive_server_1.py", "/mnt/user-data/uploads/imap_archive_server.py"):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise unittest.SkipTest("imap_archive_server.py not found; set IMAP_SERVER_PY")


def server_allows_spaces_in_logins() -> bool:
    """The newer multi-account server refuses login names containing spaces or colons."""
    return "ACCOUNT_PREFIX" not in find_server_script().read_text(encoding="utf-8")


def _load_module(script: Path):
    spec = importlib.util.spec_from_file_location("imap_archive_server_under_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def start_server(tmp: Path, repo: Path, user="me", password="secret"):
    """Starts imap_archive_server.py on `repo`; returns (process, port). Understands both configuration formats:
    the old single-account one ([repository] + [auth] user/password) and the newer multi-account one
    ([account:LOGIN] sections + a salted-hash password file). Values are written exactly as an operator would type them."""
    script = find_server_script()
    port = free_port()
    ini = tmp / f"server-{port}.ini"
    if "ACCOUNT_PREFIX" in script.read_text(encoding="utf-8"):
        module = _load_module(script)
        passwd = tmp / f"server-{port}.passwd"
        passwd.write_text(f"{user.lower()}:{module.hash_password(password)}\n", encoding="utf-8")
        passwd.chmod(0o600)
        ini.write_text(f"[server]\nhost = 127.0.0.1\nport = {port}\n[auth]\npassword_file = {passwd}\n"
                       f"[account:{user}]\npath = {repo}\n", encoding="utf-8")
    else:
        ini.write_text(f"[repository]\npath = {repo}\n[server]\nhost = 127.0.0.1\nport = {port}\n"
                       f"[auth]\nuser = {user}\npassword = {password}\n", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(script), "--config", str(ini)], stderr=subprocess.PIPE)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    return proc, port


class HangingImapServer:
    """A tiny IMAP server for timeout/cancel tests. Greets, accepts any login, and then:
      * LIST never gets an answer (a server that has stopped responding);
      * UID SEARCH is answered after `search_delay` seconds (a slow search)."""

    def __init__(self, search_delay: float = 0.0):
        self.search_delay = search_delay
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        self.list_requests = 0
        self.search_requests = 0
        self.logins = []                     # the raw text after the tag of every LOGIN command received
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
                self.logins.append(rest)
                f.write(f"{tag} OK logged in\r\n".encode())
            elif command == "EXAMINE":
                f.write(b"* 3 EXISTS\r\n" + f"{tag} OK [READ-ONLY] done\r\n".encode())
            elif command == "UID" and rest.upper().split(" ")[1] == "SEARCH":
                self.search_requests += 1
                time.sleep(self.search_delay)
                f.write(b"* SEARCH 1 2 3\r\n" + f"{tag} OK done\r\n".encode())
            elif command == "LIST":
                self.list_requests += 1
                self.got_list.set()                      # ...and never answer
            elif command == "LOGOUT":
                f.write(f"{tag} OK bye\r\n".encode())
                return

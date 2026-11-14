"""Starts the real imap_archive_server.py on a synthetic repository (shared by tests)."""
import os
import socket
import subprocess
import sys
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
                      "/mnt/user-data/uploads/imap_archive_server.py"):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise unittest.SkipTest("imap_archive_server.py not found; set IMAP_SERVER_PY")


def start_server(tmp: Path, repo: Path, user="me", password="secret"):
    """Returns (process, port). Values are written to the .ini exactly as an operator would type them."""
    port = free_port()
    ini = tmp / f"server-{port}.ini"
    ini.write_text(f"[repository]\npath = {repo}\n[server]\nhost = 127.0.0.1\nport = {port}\n"
                   f"[auth]\nuser = {user}\npassword = {password}\n", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(find_server_script()), "--config", str(ini)], stderr=subprocess.PIPE)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    return proc, port

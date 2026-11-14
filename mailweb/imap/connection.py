"""One IMAP connection plus a thread-safe gateway that reconnects on failure."""
from __future__ import annotations

import imaplib
import logging
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar

from ..errors import MailWebError, NotFound, UpstreamError
from . import utf7
from .responses import FetchRecord, parse_fetch, parse_list, parse_status, parse_status_lines

log = logging.getLogger(__name__)
T = TypeVar("T")

# Connection-level failures worth one reconnect-and-retry.
TRANSIENT = (imaplib.IMAP4.abort, OSError, EOFError)


@dataclass(frozen=True)
class ImapEndpoint:
    """Everything needed to open one IMAP connection."""
    host: str
    port: int
    user: str
    password: str
    tls: bool = False
    tls_verify: bool = True
    timeout: int = 30


def _reason(exc: Exception) -> str:
    """imaplib puts server text (often bytes) in exc.args; make it readable."""
    first = exc.args[0] if exc.args else exc
    return first.decode("utf-8", "replace") if isinstance(first, bytes) else str(first)


def quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _mailbox_arg(name: str) -> str:
    return quote(utf7.encode(name))


def _login(client: imaplib.IMAP4, user: str, password: str) -> None:
    """LOGIN with both credentials as UTF-8 quoted strings.

    imaplib.login() sends the user name as a bare token (so spaces or quotes break it) and
    encodes everything as ASCII (so non-ASCII credentials raise). Quoted strings are valid
    for any user name, on any server, so use them for both.
    """
    typ, data = client._simple_command("LOGIN", quote(user).encode("utf-8"), quote(password).encode("utf-8"))
    if typ != "OK":
        raise client.error(data[-1])
    client.state = "AUTH"


class ImapConnection:
    """Thin, typed wrapper over imaplib. Always read-only (EXAMINE)."""

    def __init__(self, endpoint: ImapEndpoint):
        self._endpoint = endpoint
        self._client: Optional[imaplib.IMAP4] = None
        self._selected: Optional[str] = None
        self._exists = 0
        self._caps: frozenset = frozenset()

    # -- lifecycle ---------------------------------------------------------
    def ensure_connected(self) -> None:
        if self._client is not None:
            return
        try:
            self._client = self._open()
        except (OSError, EOFError) as exc:
            # Failing to connect at all is not a dropped session: report it, don't retry.
            message = self._describe_connect_failure(exc)
            log.warning("%s", message)
            raise UpstreamError(message) from exc
        self._selected = None
        self._caps = self._read_capabilities()
        log.info("connected to IMAP server %s:%s", self._endpoint.host, self._endpoint.port)

    def _open(self) -> imaplib.IMAP4:
        s = self._endpoint
        if s.tls:
            ctx = ssl.create_default_context()
            if not s.tls_verify:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            client = imaplib.IMAP4_SSL(s.host, s.port, ssl_context=ctx, timeout=s.timeout)
        else:
            client = imaplib.IMAP4(s.host, s.port, timeout=s.timeout)
        try:
            _login(client, s.user, s.password)
        except BaseException:
            try:
                client.shutdown()                      # close the socket of a failed login
            except Exception:
                pass
            raise
        return client

    def _read_capabilities(self) -> frozenset:
        try:
            typ, data = self._client.capability()
            return frozenset(data[0].decode("ascii", "replace").upper().split()) if typ == "OK" and data and data[0] else frozenset()
        except Exception:
            return frozenset()

    def _describe_connect_failure(self, exc: Exception) -> str:
        s = self._endpoint
        where = f"{s.host}:{s.port}"
        if isinstance(exc, ConnectionRefusedError):
            return (f"Cannot connect to {where}: connection refused. Nothing is listening there. Check the port "
                    "and that the server is running. The address is used from the computer running mailweb, "
                    "so \"localhost\" means that computer.")
        if isinstance(exc, socket.gaierror):
            return f"Cannot connect to {where}: the host name could not be resolved."
        if isinstance(exc, (socket.timeout, TimeoutError)):
            return f"Cannot connect to {where}: timed out. Check the address and any firewall."
        if isinstance(exc, ssl.SSLCertVerificationError):
            return f"Cannot connect to {where}: certificate not trusted. For a self-signed certificate, untick certificate verification."
        if isinstance(exc, ssl.SSLError):
            return f"Cannot connect to {where}: TLS handshake failed. Is TLS ticked only for a TLS port?"
        return f"Cannot connect to {where}: {exc}"

    def reset(self) -> None:
        client, self._client, self._selected = self._client, None, None
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass

    # -- commands ----------------------------------------------------------
    def list_folders(self) -> list[str]:
        typ, data = self._client.list()
        self._check(typ, data, "LIST")
        return [entry.name for entry in parse_list(data) if entry.selectable]

    def list_folders_with_counts(self) -> list[tuple[str, int, int]]:
        """(name, messages, unseen) for every selectable folder.

        One round trip when the server has LIST-STATUS (Gmail does); otherwise one STATUS per folder.
        """
        if "LIST-STATUS" in self._caps:
            try:
                return self._list_with_status()
            except UpstreamError as exc:
                log.info("LIST-STATUS did not work (%s); using one STATUS per folder", exc)
        result = []
        for name in self.list_folders():
            try:
                messages, unseen = self.folder_status(name)
            except UpstreamError as exc:          # one odd folder must not hide the rest
                log.warning("no STATUS for folder %r: %s", name, exc)
                messages = unseen = 0
            result.append((name, messages, unseen))
        return result

    def _list_with_status(self) -> list[tuple[str, int, int]]:
        typ, data = self._client.xatom("LIST", '""', '"*"', "RETURN", "(STATUS (MESSAGES UNSEEN))")
        self._check(typ, data, "LIST")
        entries = parse_list(self._client.response("LIST")[1])
        counts = parse_status_lines(self._client.response("STATUS")[1])
        return [(e.name, *counts.get(e.name, (0, 0))) for e in entries if e.selectable]

    def folder_status(self, name: str) -> tuple[int, int]:
        typ, data = self._client.status(_mailbox_arg(name), "(MESSAGES UNSEEN)")
        self._check(typ, data, "STATUS")
        values = parse_status(data)
        return values.get("MESSAGES", 0), values.get("UNSEEN", 0)

    def select_folder(self, name: str, refresh: bool = False) -> int:
        """EXAMINE a folder (skipped if already selected) and return its message count."""
        if self._selected == name and not refresh:
            return self._exists
        try:
            typ, data = self._client.select(_mailbox_arg(name), readonly=True)
        except imaplib.IMAP4.abort:
            raise
        except imaplib.IMAP4.error:
            self._selected = None
            raise NotFound(f"no such folder: {name}") from None
        if typ == "NO":                      # some imaplib versions return NO instead of raising
            self._selected = None
            raise NotFound(f"no such folder: {name}")
        self._check(typ, data, "SELECT")
        self._selected = name
        self._exists = int(data[0]) if data and data[0] else 0
        return self._exists

    def uid_search(self, criteria: list[bytes]) -> list[int]:
        args: list[bytes] = []
        if any(not part.isascii() for part in criteria):
            args += [b"CHARSET", b"UTF-8"]
        args += criteria or [b"ALL"]
        typ, data = self._client.uid("SEARCH", *args)
        self._check(typ, data, "SEARCH")
        return [int(n) for n in (data[0] or b"").split()]

    def uid_fetch(self, uid_set: str, items: str) -> list[FetchRecord]:
        typ, data = self._client.uid("FETCH", uid_set, items)
        self._check(typ, data, "FETCH")
        return parse_fetch(data)

    @staticmethod
    def _check(typ, data, what: str) -> None:
        if typ != "OK":
            raise UpstreamError(f"IMAP {what} failed: {data!r}")


class ImapGateway:
    """A small pool of connections, so a slow request (the folder list, a big search) does not block the others.

    Usage: gateway.run(lambda imap: imap.select_folder("INBOX")).
    An operation may be re-run once after a dropped connection, so it must be idempotent
    (every operation here is read-only). The most recently used connection is reused first, so a
    folder that is already selected usually stays selected.
    """

    SLOW_SECONDS = 1.0

    def __init__(self, endpoint: ImapEndpoint, size: int = 3):
        self._endpoint = endpoint
        self._size = max(1, size)
        self._idle: list[ImapConnection] = []
        self._created = 0
        self._available = threading.Condition()

    def _acquire(self) -> ImapConnection:
        with self._available:
            while True:
                if self._idle:
                    return self._idle.pop()
                if self._created < self._size:
                    self._created += 1
                    return ImapConnection(self._endpoint)
                self._available.wait()

    def _release(self, conn: ImapConnection) -> None:
        with self._available:
            self._idle.append(conn)
            self._available.notify()

    def run(self, operation: Callable[[ImapConnection], T]) -> T:
        conn = self._acquire()
        started = time.monotonic()
        try:
            return self._run_on(conn, operation)
        except MailWebError:
            raise
        except BaseException:
            conn.reset()                      # unknown state: start from a fresh connection next time
            raise
        finally:
            self._release(conn)
            elapsed = time.monotonic() - started
            name = getattr(operation, "__qualname__", "operation")
            log.log(logging.INFO if elapsed >= self.SLOW_SECONDS else logging.DEBUG,
                    "IMAP %s took %.2fs", name, elapsed)

    @staticmethod
    def _run_on(conn: ImapConnection, operation: Callable[[ImapConnection], T]) -> T:
        for attempt in (1, 2):
            try:
                conn.ensure_connected()
                return operation(conn)
            except MailWebError:
                raise
            except TRANSIENT as exc:
                log.warning("IMAP connection problem (attempt %d): %s", attempt, exc)
                conn.reset()
                if attempt == 2:
                    raise UpstreamError(f"IMAP server unavailable: {exc}") from exc
            except imaplib.IMAP4.error as exc:
                raise UpstreamError(f"IMAP error: {_reason(exc)}") from exc
        raise AssertionError("unreachable")

    def close(self) -> None:
        with self._available:
            for conn in self._idle:
                conn.reset()

"""Adapter between http.server and Application. The only module that touches sockets."""
from __future__ import annotations

import logging
import re
import socket
import sys
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote, urlsplit

from ..config import ConfigError
from .app import Application
from .http import Request, Response, json_response

log = logging.getLogger(__name__)
MAX_BODY = 64 * 1024
HANDSHAKE_TIMEOUT = 10          # seconds a new connection gets to start speaking TLS
_SAFE_HOST = re.compile(r"^[A-Za-z0-9.\-\[\]:]+$")
_SAFE_PATH = re.compile(r"^/[^\s]*$")


def _handler_class(app: Application):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "mailweb"

        def setup(self):
            # Runs in this connection's thread, so one slow or silent client can never block the others.
            context = self.server.tls_context
            if context is not None:
                self.request = _accept_tls(self.request, context)
            super().setup()

        def log_message(self, fmt, *args):
            log.debug("%s %s", self.address_string(), fmt % args)

        def _handle(self):
            try:
                self._handle_request()
            except (BrokenPipeError, ConnectionResetError):
                pass                                   # the browser went away
            except Exception:
                log.exception("unexpected error serving %s %s", self.command, self.path)
                self._send(json_response({"error": "internal server error"}, 500))

        def _handle_request(self):
            parts = urlsplit(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._send(json_response({"error": "request too large"}, 413))
                return
            request = Request(
                method=self.command, path=unquote(parts.path),
                query=dict(parse_qsl(parts.query, keep_blank_values=True)),
                headers={k.lower(): v for k, v in self.headers.items()},
                body=self.rfile.read(length) if length else b"")
            self._send(app.handle(request))

        def _send(self, response: Response):
            try:
                self.send_response(response.status)
                for name, value in response.headers.items():
                    self.send_header(name, value)
                for cookie in response.cookies:
                    self.send_header("Set-Cookie", cookie)
                self.send_header("Content-Length", str(len(response.body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(response.body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        do_GET = do_POST = do_PATCH = do_DELETE = do_HEAD = _handle

    return Handler


def _refuse_passphrase():
    raise ConfigError("the TLS private key is protected by a passphrase; use an unencrypted key file "
                      "(for example: openssl rsa -in key.pem -out key-plain.pem)")


def load_tls_context(cert: str, key: str) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        context.load_cert_chain(cert, key, password=_refuse_passphrase)
    except FileNotFoundError as exc:
        raise ConfigError(f"TLS file not found: {exc.filename}") from None
    except ssl.SSLError as exc:
        raise ConfigError(f"cannot use the TLS certificate/key ({exc.reason or exc}). cert must be a PEM certificate "
                          "and key the matching PEM private key.") from None
    return context


def _accept_tls(sock: socket.socket, context: ssl.SSLContext) -> ssl.SSLSocket:
    sock.settimeout(HANDSHAKE_TIMEOUT)
    first = sock.recv(1, socket.MSG_PEEK)
    if not first:
        raise ConnectionAbortedError("client connected and closed without sending anything")
    if first != b"\x16":                                   # not a TLS ClientHello: someone used http:// on the HTTPS port
        _redirect_to_https(sock)
        raise ConnectionAbortedError("plain HTTP on the HTTPS port (redirected)")
    secured = context.wrap_socket(sock, server_side=True)
    secured.settimeout(None)
    return secured


def _redirect_to_https(sock: socket.socket) -> None:
    """Answer a plain-HTTP request with a (temporary) redirect to the same address over https."""
    try:
        lines = sock.recv(4096).decode("latin-1").split("\r\n")
        parts = lines[0].split(" ")
        path = parts[1] if len(parts) > 1 else "/"
        host = next((line.split(":", 1)[1].strip() for line in lines[1:] if line.lower().startswith("host:")), "")
        if _SAFE_HOST.match(host) and _SAFE_PATH.match(path):
            reply = f"HTTP/1.1 307 Temporary Redirect\r\nLocation: https://{host}{path}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        else:
            body = "This port speaks HTTPS. Use https:// in the address.\n"
            reply = f"HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n{body}"
        sock.sendall(reply.encode("latin-1"))
    except OSError:
        pass


class _Httpd(ThreadingHTTPServer):
    daemon_threads = True
    tls_context: ssl.SSLContext | None = None

    def handle_error(self, request, client_address):
        error = sys.exc_info()[1]
        if isinstance(error, (ssl.SSLError, ConnectionError, TimeoutError, socket.timeout)):
            log.debug("connection from %s ended early: %s", client_address[0], error)      # scanners, aborted handshakes
        else:
            super().handle_error(request, client_address)


class WebServer:
    def __init__(self, app: Application, host: str, port: int, cert: str = "", key: str = ""):
        context = load_tls_context(cert, key) if cert else None       # fail before binding the port
        self.httpd = _Httpd((host, port), _handler_class(app))
        self.httpd.tls_context = context
        self.tls = context is not None

    def serve_forever(self) -> None:
        self.httpd.serve_forever()

    def shutdown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

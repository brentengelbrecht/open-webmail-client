"""Adapter between http.server and Application. The only module that touches sockets."""
from __future__ import annotations

import logging
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote, urlsplit

from .app import Application
from .http import Request, Response, json_response

log = logging.getLogger(__name__)
MAX_BODY = 64 * 1024


def _handler_class(app: Application):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "mailweb"

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

        do_GET = do_POST = do_DELETE = do_HEAD = _handle

    return Handler


class WebServer:
    def __init__(self, app: Application, host: str, port: int, cert: str = "", key: str = ""):
        self.httpd = ThreadingHTTPServer((host, port), _handler_class(app))
        self.httpd.daemon_threads = True
        self.tls = bool(cert)
        if cert:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(cert, key)
            self.httpd.socket = ctx.wrap_socket(self.httpd.socket, server_side=True)

    def serve_forever(self) -> None:
        self.httpd.serve_forever()

    def shutdown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

"""Application: dispatch, authentication gate, error mapping, security headers."""
from __future__ import annotations

import logging

from ..errors import BadRequest, Cancelled, MailWebError, NotFound, Unauthorized, UpstreamError
from .context import AppContext
from .http import Request, Response, json_response
from .router import Router
from .routes import register_routes
from .sessions import Authenticator
from .static_files import StaticFiles

log = logging.getLogger(__name__)

_STATUS = ((BadRequest, 400), (Unauthorized, 401), (NotFound, 404), (UpstreamError, 502), (Cancelled, 499))

_APP_CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "frame-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'")
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "SAMEORIGIN",
    "Content-Security-Policy": _APP_CSP,
}


class Application:
    def __init__(self, context: AppContext, static: StaticFiles):
        self._auth: Authenticator = context.auth
        self._static = static
        self._router = Router()
        register_routes(self._router, context)

    def handle(self, request: Request) -> Response:
        try:
            response = self._dispatch(request)
        except MailWebError as exc:
            status = next((code for cls, code in _STATUS if isinstance(exc, cls)), 500)
            response = json_response({"error": str(exc)}, status)
        except Exception:
            log.exception("unhandled error for %s %s", request.method, request.path)
            response = json_response({"error": "internal server error"}, 500)
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    def _dispatch(self, request: Request) -> Response:
        if request.path.startswith("/api/"):
            route = self._router.match(request.method, request.path)
            if route is None:
                raise NotFound("no such endpoint")
            if not route.public and not self._auth.is_authenticated(request):
                raise Unauthorized("login required")
            return route.handler(request)
        if request.method not in ("GET", "HEAD"):
            raise BadRequest("method not allowed")
        response = self._static.serve(request.path)
        if response is None:
            raise NotFound("not found")
        return response

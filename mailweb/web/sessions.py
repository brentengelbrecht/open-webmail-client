"""Login sessions: random tokens in memory, delivered as an HttpOnly cookie."""
from __future__ import annotations

import hmac
import secrets
import threading
import time

from .http import Request

COOKIE_NAME = "mailweb_session"


class SessionStore:
    def __init__(self, ttl_seconds: int, clock=time.monotonic):
        self.ttl = ttl_seconds
        self._clock = clock
        self._expires: dict[str, float] = {}
        self._lock = threading.Lock()

    def create(self) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            now = self._clock()
            self._expires = {t: e for t, e in self._expires.items() if e > now}
            self._expires[token] = now + self.ttl
        return token

    def is_valid(self, token: str | None) -> bool:
        with self._lock:
            return bool(token) and self._expires.get(token, 0) > self._clock()

    def remaining(self, token: str | None) -> int:
        """Whole seconds until the session expires (0 if unknown or expired)."""
        with self._lock:
            return max(0, int(self._expires.get(token or "", 0) - self._clock()))

    def destroy(self, token: str | None) -> None:
        with self._lock:
            self._expires.pop(token or "", None)


class Authenticator:
    """Single shared password -> session cookie."""

    def __init__(self, password: str, sessions: SessionStore, secure_cookie: bool):
        self._password = password.encode()
        self.sessions = sessions
        self._secure = secure_cookie

    def check_password(self, supplied: str) -> bool:
        return hmac.compare_digest(supplied.encode(), self._password)

    def token_of(self, request: Request) -> str | None:
        return request.cookies.get(COOKIE_NAME)

    def is_authenticated(self, request: Request) -> bool:
        return self.sessions.is_valid(self.token_of(request))

    def remaining_seconds(self, request: Request) -> int:
        return self.sessions.remaining(self.token_of(request))

    def cookie_for(self, token: str) -> str:
        return self._cookie(token, self.sessions.ttl)

    def expired_cookie(self) -> str:
        return self._cookie("", 0)

    def _cookie(self, value: str, max_age: int) -> str:
        return (f"{COOKIE_NAME}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"
                + ("; Secure" if self._secure else ""))

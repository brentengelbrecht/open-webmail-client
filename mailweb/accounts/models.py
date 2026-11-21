"""Account value objects and validation of user-supplied account details."""
from __future__ import annotations

import secrets
from dataclasses import dataclass

from ..errors import BadRequest
from ..imap import ImapEndpoint


@dataclass(frozen=True)
class AccountInfo:
    """What the browser may see: never the password."""
    id: str
    name: str
    host: str
    port: int
    user: str
    tls: bool
    tls_verify: bool


@dataclass(frozen=True)
class Account:
    id: str
    name: str
    host: str
    port: int
    user: str
    password: str
    tls: bool = False
    tls_verify: bool = True

    def info(self) -> AccountInfo:
        return AccountInfo(self.id, self.name, self.host, self.port, self.user, self.tls, self.tls_verify)

    def endpoint(self, timeout: int, search_timeout: int = 600) -> ImapEndpoint:
        return ImapEndpoint(self.host, self.port, self.user, self.password, self.tls, self.tls_verify, timeout, search_timeout)

    MAX_NAME = 80

    @classmethod
    def from_payload(cls, data: dict) -> "Account":
        return cls._build(secrets.token_hex(4), data)

    def updated(self, changes: dict) -> "Account":
        """A copy with the given fields changed; fields not mentioned keep their value. A blank or missing
        password keeps the current one. A display name that is still the automatic user@host follows changes to them."""
        merged = {"name": self.name, "host": self.host, "port": self.port, "user": self.user,
                  "password": self.password, "tls": self.tls, "tls_verify": self.tls_verify}
        for key in merged:
            if key in changes and not (key == "password" and not changes[key]):
                merged[key] = changes[key]
        if "name" not in changes and self.name == f"{self.user}@{self.host}":
            merged["name"] = ""
        return self._build(self.id, merged)

    @classmethod
    def _build(cls, account_id: str, data: dict) -> "Account":
        def text(key: str) -> str:
            value = data.get(key)
            value = value.strip() if isinstance(value, str) else ""
            if not value:
                raise BadRequest(f"{key} is required")
            return value

        def flag(key: str, default: bool) -> bool:
            value = data.get(key, default)
            if not isinstance(value, bool):
                raise BadRequest(f"{key} must be true or false")
            return value

        host, user = text("host"), text("user")
        password = data.get("password")
        if not isinstance(password, str) or not password:
            raise BadRequest("password is required")
        try:
            port = int(data.get("port"))
        except (TypeError, ValueError):
            raise BadRequest("port must be a number") from None
        if not 1 <= port <= 65535:
            raise BadRequest("port must be between 1 and 65535")
        name = data.get("name", "")
        if name is not None and not isinstance(name, str):
            raise BadRequest("name must be text")
        name = " ".join((name or "").split())
        if len(name) > cls.MAX_NAME:
            raise BadRequest(f"name is too long (at most {cls.MAX_NAME} characters)")
        return cls(id=account_id, name=name or f"{user}@{host}", host=host, port=port, user=user, password=password,
                   tls=flag("tls", False), tls_verify=flag("tls_verify", True))

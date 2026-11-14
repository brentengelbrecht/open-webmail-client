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
        return AccountInfo(self.id, self.name, self.host, self.port, self.user, self.tls)

    def endpoint(self, timeout: int) -> ImapEndpoint:
        return ImapEndpoint(self.host, self.port, self.user, self.password, self.tls, self.tls_verify, timeout)

    @classmethod
    def from_payload(cls, data: dict) -> "Account":
        def text(key: str, required: bool = True) -> str:
            value = data.get(key)
            value = value.strip() if isinstance(value, str) else ""
            if required and not value:
                raise BadRequest(f"{key} is required")
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
        return cls(id=secrets.token_hex(4), name=text("name", required=False) or f"{user}@{host}",
                   host=host, port=port, user=user, password=password,
                   tls=bool(data.get("tls")), tls_verify=bool(data.get("tls_verify", True)))

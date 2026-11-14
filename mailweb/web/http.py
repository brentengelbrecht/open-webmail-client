"""Framework-free Request/Response types and response helpers."""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from datetime import datetime
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import quote

from ..errors import BadRequest


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)   # lower-cased names
    body: bytes = b""

    @property
    def cookies(self) -> dict[str, str]:
        jar = SimpleCookie(self.headers.get("cookie", ""))
        return {k: m.value for k, m in jar.items()}

    def param(self, name: str, default: str = "") -> str:
        return self.query.get(name, default)

    def required(self, name: str) -> str:
        value = self.query.get(name)
        if not value:
            raise BadRequest(f"missing parameter: {name}")
        return value

    def flag(self, name: str) -> bool:
        return self.query.get(name, "").lower() in ("1", "true", "yes")

    def int_param(self, name: str, default: int | None = None, minimum: int | None = None) -> int:
        raw = self.query.get(name)
        if raw in (None, ""):
            if default is None:
                raise BadRequest(f"missing parameter: {name}")
            return default
        try:
            value = int(raw)
        except ValueError:
            raise BadRequest(f"parameter {name} must be an integer") from None
        if minimum is not None and value < minimum:
            raise BadRequest(f"parameter {name} must be at least {minimum}")
        return value

    def json(self) -> dict:
        try:
            data = json.loads(self.body or b"{}")
        except ValueError:
            raise BadRequest("request body is not valid JSON") from None
        if not isinstance(data, dict):
            raise BadRequest("request body must be a JSON object")
        return data


@dataclass
class Response:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    cookies: list[str] = field(default_factory=list)       # Set-Cookie values


def _json_default(obj: Any):
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    raise TypeError(f"cannot serialise {type(obj).__name__}")


def json_response(data: Any, status: int = 200, cookies: list[str] | None = None) -> Response:
    body = json.dumps(data, default=_json_default).encode("utf-8")
    return Response(status, body, {"Content-Type": "application/json; charset=utf-8",
                                   "Cache-Control": "no-store"}, cookies or [])


def html_response(text: str, headers: dict[str, str] | None = None) -> Response:
    return Response(200, text.encode("utf-8"), {"Content-Type": "text/html; charset=utf-8",
                                                "Cache-Control": "no-store", **(headers or {})})


def file_response(data: bytes, content_type: str, filename: str) -> Response:
    ascii_name = "".join(c if c.isascii() and c.isprintable() and c not in '"\\/' else "_" for c in filename)
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    return Response(200, data, {"Content-Type": content_type or "application/octet-stream",
                                "Content-Disposition": disposition, "Cache-Control": "no-store"})

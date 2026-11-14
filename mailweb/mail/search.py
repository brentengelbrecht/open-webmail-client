"""Gmail-style query string -> IMAP SEARCH criteria.

Supported: free words, "quoted phrases", from: to: cc: subject:, is:unread|read|starred,
after:YYYY-MM-DD, before:YYYY-MM-DD. To add an operator, add an entry to OPERATORS.
"""
from __future__ import annotations

import shlex
from datetime import datetime
from typing import Callable

from ..errors import BadRequest

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _quoted(value: str) -> bytes:
    return b'"' + value.encode("utf-8").replace(b"\\", b"\\\\").replace(b'"', b'\\"') + b'"'


def _header(keyword: bytes) -> Callable[[str], list[bytes]]:
    return lambda value: [keyword, _quoted(value)]


def _flag(value: str) -> list[bytes]:
    try:
        return {"unread": [b"UNSEEN"], "read": [b"SEEN"], "starred": [b"FLAGGED"]}[value.lower()]
    except KeyError:
        raise BadRequest(f"unknown is: value {value!r} (use unread, read or starred)") from None


def _date(keyword: bytes) -> Callable[[str], list[bytes]]:
    def build(value: str) -> list[bytes]:
        try:
            d = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise BadRequest(f"bad date {value!r}, expected YYYY-MM-DD") from None
        return [keyword, f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}".encode()]
    return build


def _free_text(word: str) -> list[bytes]:
    """A bare word. The server's TEXT search sees raw (still MIME-encoded) bytes, so
    also match the decoded Subject, which is what makes non-ASCII subjects findable."""
    quoted = _quoted(word)
    return [b"OR", b"SUBJECT", quoted, b"TEXT", quoted]


OPERATORS: dict[str, Callable[[str], list[bytes]]] = {
    "from": _header(b"FROM"), "to": _header(b"TO"), "cc": _header(b"CC"),
    "subject": _header(b"SUBJECT"), "is": _flag,
    "after": _date(b"SINCE"), "before": _date(b"BEFORE"),
}


def build_criteria(query: str) -> list[bytes]:
    try:
        tokens = shlex.split(query)
    except ValueError:
        tokens = query.split()
    criteria: list[bytes] = []
    for token in tokens:
        key, _, value = token.partition(":")
        operator = OPERATORS.get(key.lower())
        if operator and value:
            criteria += operator(value)
        else:
            criteria += _free_text(token)
    return criteria

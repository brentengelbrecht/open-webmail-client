"""Parsers for the (awkward) response shapes imaplib hands back."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional

from . import utf7

_LIST_RE = re.compile(rb'^\((?P<attrs>[^)]*)\)\s+(?:"[^"]*"|NIL)\s+(?P<name>.+)$', re.S)


def unquote(token: bytes) -> bytes:
    token = token.strip()
    if token.startswith(b'"') and token.endswith(b'"') and len(token) >= 2:
        return re.sub(rb"\\(.)", rb"\1", token[1:-1])
    return token


@dataclass(frozen=True)
class ListEntry:
    name: str
    attributes: frozenset            # lower-cased, e.g. {"\\noselect", "\\haschildren"}

    @property
    def selectable(self) -> bool:
        """Gmail's "[Gmail]" parent, for example, is listed but cannot be opened."""
        return not self.attributes & {"\\noselect", "\\nonexistent"}


def parse_list(data: Iterable) -> list[ListEntry]:
    """LIST data -> folders with decoded names and their attributes."""
    entries = []
    for item in data:
        head = item[0] if isinstance(item, tuple) else item
        if not isinstance(head, bytes) or not (match := _LIST_RE.match(head.strip() if not isinstance(item, tuple) else head.split(b"{")[0].strip() + b' ""')):
            continue
        raw = item[1] if isinstance(item, tuple) else unquote(match.group("name"))     # name may be a literal
        attributes = frozenset(match.group("attrs").decode("ascii", "replace").lower().split())
        entries.append(ListEntry(utf7.decode(raw.decode("utf-8", "replace")), attributes))
    return entries


def parse_status(data: Iterable) -> dict[str, int]:
    """STATUS data -> {"MESSAGES": n, "UNSEEN": n, ...}."""
    for item in data:
        if isinstance(item, bytes):
            inner = item[item.rfind(b"(") + 1:]
            return {k.decode().upper(): int(v) for k, v in re.findall(rb"(\w+)\s+(\d+)", inner)}
    return {}


_STATUS_LINE = re.compile(rb'^\s*(?P<name>"(?:[^"\\]|\\.)*"|[^\s"]+)\s+\((?P<items>[^)]*)\)')


def parse_status_lines(data: Iterable) -> dict[str, tuple[int, int]]:
    """Untagged STATUS lines (from LIST-STATUS) -> {folder name: (messages, unseen)}."""
    counts = {}
    for item in data:
        match = _STATUS_LINE.match(item) if isinstance(item, bytes) else None
        if not match:
            continue
        name = utf7.decode(unquote(match.group("name")).decode("utf-8", "replace"))
        values = {k.decode().upper(): int(v) for k, v in re.findall(rb"(\w+)\s+(\d+)", match.group("items"))}
        counts[name] = (values.get("MESSAGES", 0), values.get("UNSEEN", 0))
    return counts


@dataclass
class FetchRecord:
    uid: Optional[int] = None
    flags: frozenset = field(default_factory=frozenset)
    internal_date: Optional[datetime] = None
    size: Optional[int] = None
    literal: Optional[bytes] = None          # the single BODY[...] literal, if requested


_UID = re.compile(rb"\bUID (\d+)")
_FLAGS = re.compile(rb"\bFLAGS \(([^)]*)\)")
_DATE = re.compile(rb'\bINTERNALDATE "([^"]+)"')
_SIZE = re.compile(rb"\bRFC822\.SIZE (\d+)")
_START = re.compile(rb"^\s*\d+ \(")


def _scan(record: FetchRecord, text: bytes) -> None:
    if (m := _UID.search(text)) and record.uid is None:
        record.uid = int(m.group(1))
    if m := _FLAGS.search(text):
        record.flags = frozenset(m.group(1).decode().split())
    if (m := _DATE.search(text)) and record.internal_date is None:
        record.internal_date = datetime.strptime(m.group(1).decode(), "%d-%b-%Y %H:%M:%S %z")
    if (m := _SIZE.search(text)) and record.size is None:
        record.size = int(m.group(1))


def parse_fetch(data: Iterable) -> list[FetchRecord]:
    """FETCH data -> one record per message (records without a UID are dropped)."""
    records: list[FetchRecord] = []
    current: Optional[FetchRecord] = None
    for item in data:
        if isinstance(item, tuple):
            current = FetchRecord()
            _scan(current, item[0])
            current.literal = item[1]
            records.append(current)
        elif isinstance(item, bytes):
            if _START.match(item):
                current = FetchRecord()
                records.append(current)
            if current is not None:
                _scan(current, item)      # also handles attributes trailing a literal
    return [r for r in records if r.uid is not None]

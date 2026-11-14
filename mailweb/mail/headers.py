"""Header parsing shared by the message list and the message view."""
from __future__ import annotations

from datetime import datetime, timezone
from email import policy
from email.message import Message
from email.parser import BytesHeaderParser
from typing import Optional

from .models import Address, Envelope

_parser = BytesHeaderParser(policy=policy.default)


def parse_headers(raw: bytes) -> Message:
    return _parser.parsebytes(raw)


def _text(msg: Message, name: str) -> str:
    try:
        return " ".join(str(msg.get(name) or "").split())
    except Exception:
        return ""


def _addresses(msg: Message, name: str) -> tuple[Address, ...]:
    found = []
    try:
        for header in msg.get_all(name, []):
            for a in getattr(header, "addresses", ()):
                found.append(Address(name=a.display_name or "", email=a.addr_spec or ""))
    except Exception:
        pass
    return tuple(found)


def _date(msg: Message) -> Optional[datetime]:
    try:
        dt = getattr(msg.get("Date"), "datetime", None)
    except Exception:
        return None
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def extract_envelope(msg: Message) -> Envelope:
    senders = _addresses(msg, "From")
    return Envelope(
        subject=_text(msg, "Subject"),
        sender=senders[0] if senders else None,
        to=_addresses(msg, "To"),
        cc=_addresses(msg, "Cc"),
        date=_date(msg),
    )


def looks_like_it_has_attachments(msg: Message) -> bool:
    """Header-only heuristic (same trick mail clients use before loading bodies)."""
    return msg.get_content_type() == "multipart/mixed"

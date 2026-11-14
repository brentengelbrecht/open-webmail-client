"""Turns a raw RFC 822 message into a displayable body and a list of attachments."""
from __future__ import annotations

import base64
import html
import mimetypes
import re
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from typing import Iterator
from urllib.parse import unquote

from ..errors import NotFound
from .models import Attachment

_PREFIX = ('<meta charset="utf-8"><meta name="referrer" content="no-referrer"><base target="_blank">'
           "<style>body{font:14px/1.5 system-ui,sans-serif;margin:16px;overflow-wrap:anywhere}"
           "pre{white-space:pre-wrap;font:inherit;margin:0}.empty{color:#777}</style>")
_URL = re.compile(r"https?://[^\s<>\"']+")
_CID = re.compile(r"cid:([^\"'\s)>]+)", re.I)
_REMOTE_IMAGE = re.compile(r"""<img\b[^>]*\bsrc\s*=\s*["']?\s*(?:https?:)?//|url\(\s*["']?\s*https?:|\bbackground\s*=\s*["']?https?:""", re.I)


def _walk(part: EmailMessage) -> Iterator[EmailMessage]:
    """Like Message.walk() but does not descend into attached messages."""
    yield part
    if part.is_multipart() and part.get_content_type() != "message/rfc822":
        for sub in part.iter_parts():
            yield from _walk(sub)


def _is_attachment(part: EmailMessage) -> bool:
    ctype = part.get_content_type()
    if ctype == "message/rfc822":
        return True
    if part.is_multipart():
        return False
    disposition = part.get_content_disposition()
    if disposition == "attachment":
        return True
    if ctype in ("text/plain", "text/html") and not part.get_filename():
        return False
    if ctype.startswith("image/") and part.get("Content-ID"):
        return False                      # inline image, shown inside the HTML body
    return True


def _payload(part: EmailMessage) -> bytes:
    if part.get_content_type() == "message/rfc822":
        inner = part.get_payload(0) if part.is_multipart() else None
        return inner.as_bytes() if inner is not None else b""
    return part.get_payload(decode=True) or b""


def _decode_text(part: EmailMessage) -> str:
    try:
        return part.get_content()
    except (LookupError, UnicodeDecodeError, ValueError):
        return (part.get_payload(decode=True) or b"").decode("utf-8", "replace")


def _linkify(escaped: str) -> str:
    def link(match):
        url = match.group(0)
        tail = ""
        while url and url[-1] in ".,;:!?)":
            url, tail = url[:-1], url[-1] + tail
        return f'<a href="{url}" rel="noopener noreferrer">{url}</a>{tail}'
    return _URL.sub(link, escaped)


class MessageContent:
    """Parsed view of one raw message. Cheap to keep; parse once, ask many times."""

    def __init__(self, raw: bytes):
        self.raw = raw
        self.message: EmailMessage = BytesParser(policy=policy.default).parsebytes(raw)
        self._attachments: list[tuple[Attachment, EmailMessage]] | None = None

    def wipe(self) -> None:
        """Best effort: drop the parsed message and its attachment parts. (Python strings and bytes are
        immutable, so their old buffers are only released, not overwritten.)"""
        self.raw = b""
        self.message = None
        self._attachments = []

    # -- attachments -------------------------------------------------------
    def _attachment_parts(self) -> list[tuple[Attachment, EmailMessage]]:
        if self._attachments is None:
            found = []
            for part in _walk(self.message):
                if part is self.message and not part.is_multipart() and not _is_attachment(part):
                    continue
                if not _is_attachment(part):
                    continue
                index = len(found)
                ctype = part.get_content_type()
                name = part.get_filename() or f"attachment-{index + 1}{mimetypes.guess_extension(ctype) or ''}"
                found.append((Attachment(index, name, ctype, len(_payload(part))), part))
            self._attachments = found
        return self._attachments

    @property
    def attachments(self) -> tuple[Attachment, ...]:
        return tuple(a for a, _ in self._attachment_parts())

    def attachment(self, index: int) -> tuple[Attachment, bytes]:
        parts = self._attachment_parts()
        if not 0 <= index < len(parts):
            raise NotFound(f"no attachment {index}")
        attachment, part = parts[index]
        return attachment, _payload(part)

    # -- body --------------------------------------------------------------
    @property
    def has_remote_images(self) -> bool:
        """True if the HTML body would fetch images from the internet (if allowed)."""
        part = self.message.get_body(preferencelist=("html",))
        return part is not None and bool(_REMOTE_IMAGE.search(_decode_text(part)))

    def body_document(self) -> str:
        """A complete HTML document. Remote content is blocked by the serving CSP."""
        part = self.message.get_body(preferencelist=("html", "plain"))
        if part is None:
            return _PREFIX + '<p class="empty">(no text content)</p>'
        text = _decode_text(part)
        if part.get_content_subtype() == "html":
            return _PREFIX + self._inline_cid_images(text)
        return _PREFIX + "<pre>" + _linkify(html.escape(text)) + "</pre>"

    def _inline_cid_images(self, document: str) -> str:
        if "cid:" not in document.lower():
            return document
        images = {}
        for part in _walk(self.message):
            cid = (part.get("Content-ID") or "").strip("<> \t\r\n")
            if cid and not part.is_multipart():
                data = base64.b64encode(_payload(part)).decode()
                images[cid] = f"data:{part.get_content_type()};base64,{data}"
        return _CID.sub(lambda m: images.get(unquote(m.group(1)), m.group(0)), document)

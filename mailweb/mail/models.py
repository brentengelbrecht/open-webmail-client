"""Plain data objects. Frozen, JSON-friendly, no behaviour."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Address:
    name: str
    email: str


@dataclass(frozen=True)
class Envelope:
    subject: str
    sender: Optional[Address]
    to: tuple[Address, ...]
    cc: tuple[Address, ...]
    date: Optional[datetime]


@dataclass(frozen=True)
class Folder:
    name: str
    messages: int
    unseen: int


@dataclass(frozen=True)
class MessageMeta:
    """Cheap per-message facts the server can answer without reading files."""
    uid: int
    date: datetime
    flags: frozenset
    size: int

    @property
    def unread(self) -> bool:
        return "\\Seen" not in self.flags

    @property
    def starred(self) -> bool:
        return "\\Flagged" in self.flags


@dataclass(frozen=True)
class MessageSummary:
    uid: int
    subject: str
    sender: Optional[Address]
    date: datetime
    unread: bool
    starred: bool
    has_attachments: bool
    size: int


@dataclass(frozen=True)
class Attachment:
    index: int
    filename: str
    content_type: str
    size: int


@dataclass(frozen=True)
class MessageDetail:
    uid: int
    folder: str
    subject: str
    sender: Optional[Address]
    to: tuple[Address, ...]
    cc: tuple[Address, ...]
    date: datetime
    unread: bool
    starred: bool
    size: int
    attachments: tuple[Attachment, ...]
    remote_images_blocked: bool     # has remote images and the server is not configured to load them


@dataclass(frozen=True)
class MessagePage:
    folder: str
    page: int
    pages: int
    page_size: int
    total: int
    query: str
    items: tuple[MessageSummary, ...]

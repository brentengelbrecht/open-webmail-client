"""MailService: the only entry point the web layer uses. Orchestrates IMAP + parsing + caching."""
from __future__ import annotations

from typing import NamedTuple, Optional

from ..cache import Cache
from ..config import MailSettings
from ..errors import NotFound
from ..imap import ImapConnection, ImapGateway
from .body import MessageContent
from .folders import order_folders
from .headers import extract_envelope, looks_like_it_has_attachments, parse_headers
from .index import FolderIndex, build_index
from .models import Address, Folder, MessageDetail, MessagePage, MessageSummary
from .search import build_criteria

_LIST_HEADERS = "(UID BODY.PEEK[HEADER.FIELDS (FROM SUBJECT CONTENT-TYPE)])"


class _Header(NamedTuple):
    subject: str
    sender: Optional[Address]
    has_attachments: bool


class MailService:
    def __init__(self, gateway: ImapGateway, settings: MailSettings):
        self._gw = gateway
        self._settings = settings
        ttl = settings.index_ttl_seconds
        self._folders: Cache = Cache(maxsize=1, ttl=ttl)
        self._indexes: Cache = Cache(maxsize=16, ttl=ttl)
        self._headers: Cache = Cache(maxsize=5000)          # immutable archive: no ttl
        self._contents: Cache = Cache(maxsize=settings.message_cache)

    def purge(self) -> None:
        """Drop everything cached for this mailbox (folder list, indexes, headers, parsed messages)."""
        for content in self._contents.values():
            content.wipe()
        for cache in (self._folders, self._indexes, self._headers, self._contents):
            cache.clear()

    @property
    def load_remote_images(self) -> bool:
        """Configured default: load remote images in every message."""
        return self._settings.load_remote_images

    # -- folders -----------------------------------------------------------
    def folders(self, refresh: bool = False) -> list[Folder]:
        if refresh:
            self._folders.clear()
        cached = self._folders.get("all")
        if cached is not None:
            return cached
        return self._folders.set("all", self._gw.run(self._load_folders))

    @staticmethod
    def _load_folders(imap: ImapConnection) -> list[Folder]:
        return order_folders([Folder(name, messages, unseen) for name, messages, unseen in imap.list_folders_with_counts()])

    # -- message list ------------------------------------------------------
    def list_messages(self, folder: str, page: int = 1, query: str = "", refresh: bool = False) -> MessagePage:
        if refresh:
            self._indexes.discard(folder)
            self._folders.clear()
        metas = self._index(folder).metas
        query = query.strip()
        if query:
            criteria = build_criteria(query)
            hits = set(self._gw.run(lambda imap: self._search(imap, folder, criteria)))
            metas = tuple(m for m in metas if m.uid in hits)
        size = self._settings.page_size
        pages = max(1, -(-len(metas) // size))
        page = min(max(page, 1), pages)
        window = metas[(page - 1) * size: page * size]
        headers = self._headers_for(folder, [m.uid for m in window])
        items = tuple(
            MessageSummary(uid=m.uid, subject=headers[m.uid].subject, sender=headers[m.uid].sender,
                           date=m.date, unread=m.unread, starred=m.starred,
                           has_attachments=headers[m.uid].has_attachments, size=m.size)
            for m in window)
        return MessagePage(folder=folder, page=page, pages=pages, page_size=size,
                           total=len(metas), query=query, items=items)

    def _index(self, folder: str) -> FolderIndex:
        cached = self._indexes.get(folder)
        if cached is not None:
            return cached
        return self._indexes.set(folder, self._gw.run(lambda imap: build_index(imap, folder)))

    @staticmethod
    def _search(imap: ImapConnection, folder: str, criteria: list[bytes]) -> list[int]:
        imap.select_folder(folder)
        return imap.uid_search(criteria)

    def _headers_for(self, folder: str, uids: list[int]) -> dict[int, _Header]:
        found = {u: self._headers.get((folder, u)) for u in uids}
        missing = [u for u, h in found.items() if h is None]
        if missing:
            def fetch(imap: ImapConnection):
                imap.select_folder(folder)
                return imap.uid_fetch(",".join(map(str, missing)), _LIST_HEADERS)
            for record in self._gw.run(fetch):
                msg = parse_headers(record.literal or b"")
                env = extract_envelope(msg)
                found[record.uid] = self._headers.set(
                    (folder, record.uid), _Header(env.subject, env.sender, looks_like_it_has_attachments(msg)))
        return {u: h or _Header("", None, False) for u, h in found.items()}

    # -- single message ----------------------------------------------------
    def content(self, folder: str, uid: int) -> MessageContent:
        key = (folder, uid)
        cached = self._contents.get(key)
        if cached is not None:
            return cached
        if uid not in self._index(folder).by_uid:
            raise NotFound(f"no message {uid} in {folder}")

        def fetch(imap: ImapConnection) -> bytes:
            imap.select_folder(folder)
            for record in imap.uid_fetch(str(uid), "(UID BODY.PEEK[])"):
                if record.uid == uid and record.literal is not None:
                    return record.literal
            raise NotFound(f"no message {uid} in {folder}")

        return self._contents.set(key, MessageContent(self._gw.run(fetch)))

    def detail(self, folder: str, uid: int) -> MessageDetail:
        content = self.content(folder, uid)
        meta = self._index(folder).by_uid[uid]
        env = extract_envelope(content.message)
        return MessageDetail(uid=uid, folder=folder, subject=env.subject, sender=env.sender,
                             to=env.to, cc=env.cc, date=env.date or meta.date,
                             unread=meta.unread, starred=meta.starred, size=meta.size,
                             attachments=content.attachments,
                             remote_images_blocked=content.has_remote_images and not self.load_remote_images)

"""Per-folder index: every message's date/flags/size, newest first."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..imap import ImapConnection
from .models import MessageMeta

_EPOCH = datetime.fromtimestamp(0, timezone.utc)


@dataclass(frozen=True)
class FolderIndex:
    metas: tuple[MessageMeta, ...]
    by_uid: dict


def build_index(imap: ImapConnection, folder: str) -> FolderIndex:
    """Cheap: the server answers these attributes from its database, not from files."""
    count = imap.select_folder(folder, refresh=True)
    records = imap.uid_fetch("1:*", "(UID FLAGS INTERNALDATE RFC822.SIZE)") if count else []
    metas = [MessageMeta(uid=r.uid, date=r.internal_date or _EPOCH, flags=r.flags, size=r.size or 0)
             for r in records]
    metas.sort(key=lambda m: (m.date, m.uid), reverse=True)
    return FolderIndex(metas=tuple(metas), by_uid={m.uid: m for m in metas})

"""Folder presentation rules (ordering). Add special-folder handling here."""
from __future__ import annotations

from .models import Folder

_PRIORITY = ["inbox", "starred", "important", "sent", "sent mail", "drafts", "all mail", "spam", "trash"]


def _key(folder: Folder):
    lowered = folder.name.lower()
    rank = _PRIORITY.index(lowered) if lowered in _PRIORITY else len(_PRIORITY)
    return rank, lowered


def order_folders(folders: list[Folder]) -> list[Folder]:
    return sorted(folders, key=_key)

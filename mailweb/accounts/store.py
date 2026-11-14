"""Persists accounts in an encrypted JSON file readable only by the current user."""
from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from ..config import ConfigError
from .crypto import DecryptionError, Vault
from .models import Account

log = logging.getLogger(__name__)
FORMAT = 2


class AccountStore:
    """File layout: {"version": 2, "kdf": {...}, "salt": "<b64>", "data": "<Fernet token>"}.

    `data` holds the whole account list (hosts, user names and passwords), so nothing readable
    is left on disk. The key comes from `passphrase` (the web password) and the stored salt.
    """

    def __init__(self, path: Path | str, passphrase: str):
        self._path = Path(path)
        self._passphrase = passphrase
        self._vault: Vault | None = None
        self._lock = threading.Lock()

    def load(self) -> list[Account]:
        if not self._path.exists():
            return []
        try:
            document = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ConfigError(f"cannot read accounts file {self._path}: {exc}") from None
        if isinstance(document, list):                       # format 1: plaintext, from earlier versions
            accounts = self._parse(document)
            self.save(accounts)
            log.warning("encrypted the plaintext accounts file %s", self._path)
            return accounts
        try:
            if document["version"] != FORMAT:
                raise ConfigError(f"{self._path} has an unsupported format version")
            vault = Vault(self._passphrase, base64.b64decode(document["salt"]), document["kdf"])
            plaintext = vault.decrypt(document["data"])
        except DecryptionError:
            raise ConfigError(
                f"cannot decrypt {self._path}. Either the web password has changed since the accounts were "
                "saved (restore the old password), or the file is damaged. To start over, delete the file "
                "and add your accounts again.") from None
        except (KeyError, TypeError, binascii.Error) as exc:
            raise ConfigError(f"{self._path} is not a valid accounts file ({exc!r})") from None
        self._vault = vault
        return self._parse(json.loads(plaintext))

    def save(self, accounts: Iterable[Account]) -> None:
        with self._lock:
            if self._vault is None:
                self._vault = Vault(self._passphrase)        # new random salt for a new file
            vault = self._vault
            document = {"version": FORMAT, "kdf": {"name": "scrypt", **vault.kdf},
                        "salt": base64.b64encode(vault.salt).decode("ascii"),
                        "data": vault.encrypt(json.dumps([asdict(a) for a in accounts]).encode("utf-8"))}
            tmp = self._path.with_name(self._path.name + ".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(document, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            self._swap_in(tmp)

    def erase(self) -> None:
        """Overwrite the accounts file with "X" and delete it (used when the last account is removed)."""
        with self._lock:
            self._overwrite_and_unlink(self._path)
            self._vault = None                               # a later save starts a new file with a new salt

    def _swap_in(self, tmp: Path) -> None:
        """Atomically replace the live file, then overwrite the bytes of the old one with "X".

        The old content is kept reachable through a hard link while the new file is moved in, so the
        live path is never missing or half-written, and the old data blocks can be overwritten afterwards.
        """
        old = self._path.with_name(self._path.name + ".old")
        self._clear_leftover(old)
        linked = False
        if self._path.exists():
            try:
                os.link(self._path, old)
                linked = True
            except OSError:                                  # filesystem without hard links: just replace
                pass
        os.replace(tmp, self._path)                          # atomic: a crash never leaves half a file
        if linked:
            self._overwrite_and_unlink(old)

    def _clear_leftover(self, old: Path) -> None:
        """A '.old' left by a crash may still be the *live* file (same inode): then only unlink it."""
        if not old.exists():
            return
        if self._path.exists() and os.path.samefile(old, self._path):
            os.unlink(old)
        else:
            self._overwrite_and_unlink(old)

    @staticmethod
    def _overwrite_and_unlink(path: Path) -> None:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return
        try:
            with open(path, "r+b") as fh:
                fh.write(b"X" * size)
                fh.flush()
                os.fsync(fh.fileno())
        finally:
            os.unlink(path)

    def _parse(self, items: list) -> list[Account]:
        try:
            return [Account(**item) for item in items]
        except TypeError as exc:
            raise ConfigError(f"accounts file {self._path} has an invalid entry: {exc}") from None

"""Encryption of the accounts file. The only module that imports `cryptography`.

The IMAP passwords must be sent to the mail server in clear form on every login, so they cannot be
hashed; they are encrypted instead. Key = scrypt(web password, random salt); cipher = Fernet
(AES-128-CBC + HMAC-SHA256, authenticated, so tampering is detected).
"""
from __future__ import annotations

import base64
import hashlib
import os
import sys

from ..config import ConfigError

try:
    from cryptography.fernet import Fernet, InvalidToken
    _IMPORT_ERROR = None
except ImportError as _exc:              # reported with a helpful message when first needed
    Fernet = InvalidToken = None
    _IMPORT_ERROR = _exc

DEFAULT_KDF = {"n": 2 ** 15, "r": 8, "p": 1}           # ~32 MiB, ~0.1 s on a Raspberry Pi 4
_LIMITS = {"n": 2 ** 20, "r": 16, "p": 4}               # refuse absurd values from a tampered file
SALT_BYTES = 16


class DecryptionError(Exception):
    """Wrong passphrase, or the data was altered."""


class Vault:
    def __init__(self, passphrase: str, salt: bytes | None = None, kdf: dict | None = None):
        if Fernet is None:
            raise ConfigError(
                "the 'cryptography' package is needed to encrypt the accounts file, but this Python cannot import it "
                f"({_IMPORT_ERROR}). Python in use: {sys.executable} ({sys.version.split()[0]}). Packages are installed "
                "per Python, so install it into that one, ideally in a virtual environment: "
                "python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python run.py")
        self.salt = salt or os.urandom(SALT_BYTES)
        self.kdf = {k: int((kdf or DEFAULT_KDF)[k]) for k in DEFAULT_KDF}
        if any(not 1 <= self.kdf[k] <= _LIMITS[k] for k in _LIMITS) or self.kdf["n"] & (self.kdf["n"] - 1):
            raise ConfigError("accounts file has unsupported key-derivation settings")
        key = hashlib.scrypt(passphrase.encode("utf-8"), salt=self.salt, dklen=32,
                             maxmem=128 * 1024 * 1024, **self.kdf)
        self._fernet = Fernet(base64.urlsafe_b64encode(key))

    def encrypt(self, data: bytes) -> str:
        return self._fernet.encrypt(data).decode("ascii")

    def decrypt(self, token: str) -> bytes:
        try:
            return self._fernet.decrypt(token.encode("ascii"))
        except (InvalidToken, ValueError):
            raise DecryptionError from None

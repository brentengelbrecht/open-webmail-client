"""Owns every account and lazily builds one gateway + MailService per account."""
from __future__ import annotations

import gc
import threading

from ..config import MailSettings
from ..errors import NotFound
from ..imap import ImapGateway
from ..mail import MailService
from .models import Account, AccountInfo
from .store import AccountStore


class AccountRegistry:
    def __init__(self, store: AccountStore, settings: MailSettings):
        self._store = store
        self._settings = settings
        self._lock = threading.Lock()
        self._accounts: dict[str, Account] = {a.id: a for a in store.load()}
        self._services: dict[str, tuple[ImapGateway, MailService]] = {}

    def list(self) -> list[AccountInfo]:
        with self._lock:
            return [a.info() for a in self._accounts.values()]

    def add(self, payload: dict) -> AccountInfo:
        """Validate, prove the credentials work by connecting, then save."""
        account = Account.from_payload(payload)
        gateway = ImapGateway(account.endpoint(self._settings.imap_timeout), self._settings.imap_connections)
        try:
            gateway.run(lambda imap: imap.list_folders())     # raises UpstreamError with the reason
        except Exception:
            gateway.close()
            raise
        with self._lock:
            self._accounts[account.id] = account
            self._services[account.id] = (gateway, MailService(gateway, self._settings))
            self._store.save(self._accounts.values())
        return account.info()

    def remove(self, account_id: str) -> None:
        """Forget an account completely: saved login, open connections and everything cached for it."""
        with self._lock:
            if self._accounts.pop(account_id, None) is None:
                raise NotFound("unknown account")
            gateway, service = self._services.pop(account_id, (None, None))
            if self._accounts:
                self._store.save(self._accounts.values())    # old file contents are overwritten with "X"
            else:
                self._store.erase()
        if service:
            service.purge()
        if gateway:
            gateway.close()
        gc.collect()                                         # let the runtime release what is now unreferenced

    def service(self, account_id: str) -> MailService:
        with self._lock:
            account = self._accounts.get(account_id)
            if account is None:
                raise NotFound("unknown account")
            if account_id not in self._services:
                gateway = ImapGateway(account.endpoint(self._settings.imap_timeout), self._settings.imap_connections)
                self._services[account_id] = (gateway, MailService(gateway, self._settings))
            return self._services[account_id][1]

    def close(self) -> None:
        with self._lock:
            for gateway, _ in self._services.values():
                gateway.close()
            self._services.clear()

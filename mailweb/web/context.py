"""Dependencies handed to route modules (keeps them decoupled from construction)."""
from __future__ import annotations

from dataclasses import dataclass

from ..accounts import AccountRegistry
from ..mail import MailService
from .http import Request
from .sessions import Authenticator


@dataclass(frozen=True)
class AppContext:
    accounts: AccountRegistry
    auth: Authenticator

    def mail_for(self, request: Request) -> MailService:
        """The mailbox service for the request's ?account= parameter (one place, used by every mail route)."""
        return self.accounts.service(request.required("account"))

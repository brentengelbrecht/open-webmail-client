"""Mail accounts added at runtime through the UI."""
from .models import Account, AccountInfo
from .registry import AccountRegistry
from .store import AccountStore

__all__ = ["Account", "AccountInfo", "AccountRegistry", "AccountStore"]

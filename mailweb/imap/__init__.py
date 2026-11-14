"""IMAP access layer. Nothing outside this package speaks IMAP."""
from .connection import ImapConnection, ImapEndpoint, ImapGateway

__all__ = ["ImapConnection", "ImapEndpoint", "ImapGateway"]

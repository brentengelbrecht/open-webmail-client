"""Domain errors. The web layer maps these to HTTP statuses (web/app.py)."""


class MailWebError(Exception):
    """Base class for errors whose message is safe to show to the user."""


class BadRequest(MailWebError):
    """The caller sent something invalid."""


class Unauthorized(MailWebError):
    """Login required or credentials wrong."""


class NotFound(MailWebError):
    """A folder, message or attachment does not exist."""


class UpstreamError(MailWebError):
    """The IMAP server is unreachable or misbehaving."""

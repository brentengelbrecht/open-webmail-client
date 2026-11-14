"""Configuration: one documented .ini file, validated at startup.

The dataclasses below ARE the schema: field names are option names, defaults are
the documented defaults, and a field without a default is required. To add an
option, add a field here and document it in mailweb.ini and README.md.
(No `from __future__ import annotations` here: the loader reads real types.)
"""
import configparser
import logging
import os
from dataclasses import MISSING, dataclass, field, fields
from pathlib import Path

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


class ConfigError(Exception):
    """Any problem with the .ini file; the message is meant for the operator."""


def _opt(default, *, path=False, lo=None, hi=None, choices=None):
    return field(default=default, metadata={"path": path, "lo": lo, "hi": hi, "choices": choices})


@dataclass(frozen=True)
class WebSettings:
    host: str = "127.0.0.1"
    port: int = _opt(8080, lo=1, hi=65535)
    session_minutes: int = _opt(60, lo=1, hi=10080)
    cert: str = _opt("", path=True)
    key: str = _opt("", path=True)
    password: str = ""
    password_file: str = _opt("", path=True)
    accounts_file: str = _opt("accounts.json", path=True)


@dataclass(frozen=True)
class MailSettings:
    page_size: int = _opt(50, lo=1, hi=200)
    message_cache: int = _opt(32, lo=1, hi=1000)
    index_ttl_seconds: int = _opt(600, lo=1, hi=86400)
    imap_timeout: int = _opt(30, lo=1, hi=600)
    imap_connections: int = _opt(3, lo=1, hi=8)
    load_remote_images: bool = False


@dataclass(frozen=True)
class LoggingSettings:
    level: str = _opt("INFO", choices=LOG_LEVELS)
    file: str = _opt("", path=True)


SECTIONS = {"web": WebSettings, "mail": MailSettings, "logging": LoggingSettings}


@dataclass(frozen=True)
class Config:
    web: WebSettings
    mail: MailSettings
    logging: LoggingSettings
    web_password: str
    path: Path


def _hint(raw):
    if "\n" in raw:
        return " (the next line is indented, so it was read as part of this value; start option lines in column 1)"
    if " #" in raw or " ;" in raw:
        return " (comments must be on their own line)"
    return ""


def _convert(section, f, raw, base_dir):
    where = f"[{section}] {f.name}"
    text = raw.strip()
    if f.type is bool:
        if text.lower() not in ("true", "false", "yes", "no", "on", "off", "1", "0"):
            raise ConfigError(f"{where} must be true or false, got {raw!r}{_hint(raw)}")
        return text.lower() in ("true", "yes", "on", "1")
    if f.type is int:
        try:
            value = int(text)
        except ValueError:
            raise ConfigError(f"{where} must be an integer, got {raw!r}{_hint(raw)}") from None
        lo, hi = f.metadata.get("lo"), f.metadata.get("hi")
        if (lo is not None and value < lo) or (hi is not None and value > hi):
            raise ConfigError(f"{where} must be between {lo} and {hi}, got {value}")
        return value
    choices = f.metadata.get("choices")
    if choices:
        text = text.upper()
        if text not in choices:
            raise ConfigError(f"{where} must be one of {', '.join(choices)}, got {raw!r}")
    if f.metadata.get("path") and text:
        p = Path(text).expanduser()
        text = str(p if p.is_absolute() else base_dir / p)
    return text


def _build_section(name, cls, parser, base_dir):
    given = dict(parser.items(name)) if parser.has_section(name) else {}
    known = {f.name: f for f in fields(cls)}
    for option in given:
        if option not in known:
            raise ConfigError(f"unknown option {option!r} in [{name}] (valid: {', '.join(known)})")
    values = {}
    for fname, f in known.items():
        if fname in given:
            values[fname] = _convert(name, f, given[fname], base_dir)
        elif f.default is MISSING:
            raise ConfigError(f"[{name}] {fname} is required")
        else:
            values[fname] = _convert(name, f, str(f.default), base_dir) if f.type is not str or f.metadata.get("path") \
                else f.default
    return cls(**values)


def resolve_secret(what, env_var, file, literal):
    """Password lookup order: environment variable, then file, then literal."""
    value = os.environ.get(env_var)
    if value:
        return value
    if file:
        try:
            return Path(file).read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as exc:
            raise ConfigError(f"cannot read the {what} password file {file}: {exc.strerror}") from None
    if literal:
        return literal
    raise ConfigError(f"no {what} password: set {env_var}, password_file or password")


def load_config(path) -> Config:
    path = Path(path).expanduser().resolve()
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with open(path, encoding="utf-8") as fh:
            parser.read_file(fh)
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc.strerror}") from None
    except configparser.Error as exc:
        raise ConfigError(f"{path}: {exc}") from None
    for section in parser.sections():
        if section not in SECTIONS:
            raise ConfigError(f"unknown section [{section}] (valid: {', '.join(SECTIONS)})")
    built = {name: _build_section(name, cls, parser, path.parent) for name, cls in SECTIONS.items()}
    web = built["web"]
    if bool(web.cert) != bool(web.key):
        raise ConfigError("[web] cert and key must be set together")
    if web.password and path.stat().st_mode & 0o077:
        logging.getLogger(__name__).warning("%s holds a password and is readable by others; run chmod 600", path)
    return Config(
        web_password=resolve_secret("web login", "MAILWEB_WEB_PASSWORD", web.password_file, web.password),
        path=path, **built)

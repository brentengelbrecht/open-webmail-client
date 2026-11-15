#!/usr/bin/env python3
"""Entry point: python3 run.py [--config mailweb.ini] [-v]"""
import argparse
import logging
import signal
import sys
import threading
from pathlib import Path

from mailweb.config import ConfigError, load_config
from mailweb.accounts import AccountRegistry, AccountStore
from mailweb.web.app import Application
from mailweb.web.context import AppContext
from mailweb.web.server import WebServer
from mailweb.web.sessions import Authenticator, SessionStore
from mailweb.web.static_files import StaticFiles

# Frozen by PyInstaller (desktop build) the bundled files live under sys._MEIPASS.
HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def build_server(cfg) -> tuple[WebServer, AccountRegistry]:
    registry = AccountRegistry(AccountStore(cfg.web.accounts_file, cfg.web_password), cfg.mail)
    sessions = SessionStore(cfg.web.session_minutes * 60)
    auth = Authenticator(cfg.web_password, sessions, secure_cookie=bool(cfg.web.cert))
    context = AppContext(accounts=registry, auth=auth)
    app = Application(context, StaticFiles(HERE / "mailweb" / "web" / "static"))
    return WebServer(app, cfg.web.host, cfg.web.port, cfg.web.cert, cfg.web.key), registry


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only web client for imap_archive_server")
    parser.add_argument("--config", default=str(HERE / "mailweb.ini"))
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args()
    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.DEBUG if args.verbose else cfg.logging.level,
                        filename=cfg.logging.file or None,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        server, registry = build_server(cfg)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"cannot start web server on {cfg.web.host}:{cfg.web.port}: {exc}", file=sys.stderr)
        return 1
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    scheme = "https" if server.tls else "http"
    logging.getLogger("mailweb").info("serving %s://%s:%s", scheme, cfg.web.host, cfg.web.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    finally:
        registry.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

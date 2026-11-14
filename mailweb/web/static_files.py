"""Serves the front-end from a directory, safely."""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional

from .http import Response


class StaticFiles:
    def __init__(self, root: Path):
        self._root = root.resolve()

    def serve(self, url_path: str) -> Optional[Response]:
        relative = url_path.lstrip("/") or "index.html"
        target = (self._root / relative).resolve()
        if not target.is_relative_to(self._root) or not target.is_file():
            return None
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        return Response(200, target.read_bytes(), {"Content-Type": ctype, "Cache-Control": "no-cache"})

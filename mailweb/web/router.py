"""Exact-match router. Features register routes; the app never needs to know about them."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .http import Request, Response

Handler = Callable[[Request], Response]


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    handler: Handler
    public: bool = False       # public routes skip the login check


class Router:
    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], Route] = {}

    def add(self, method: str, path: str, handler: Handler, *, public: bool = False) -> None:
        self._routes[(method, path)] = Route(method, path, handler, public)

    def route(self, method: str, path: str, *, public: bool = False):
        def decorator(handler: Handler) -> Handler:
            self.add(method, path, handler, public=public)
            return handler
        return decorator

    def match(self, method: str, path: str) -> Optional[Route]:
        return self._routes.get((method, path))

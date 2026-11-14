"""Feature routes. Each module exposes register(router, ctx); add new ones to _MODULES."""
from ..context import AppContext
from ..router import Router
from . import accounts, auth, folders, messages

_MODULES = (auth, accounts, folders, messages)


def register_routes(router: Router, ctx: AppContext) -> None:
    for module in _MODULES:
        module.register(router, ctx)

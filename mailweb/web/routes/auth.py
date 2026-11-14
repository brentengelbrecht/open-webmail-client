"""Login / logout / session status."""
import time

from ...errors import Unauthorized
from ..http import json_response


def register(router, ctx):
    auth = ctx.auth

    @router.route("GET", "/api/session", public=True)
    def session(request):
        return json_response({"authenticated": auth.is_authenticated(request),
                              "expires_in": auth.remaining_seconds(request)})

    @router.route("POST", "/api/login", public=True)
    def login(request):
        if not auth.check_password(str(request.json().get("password", ""))):
            time.sleep(1)                      # slows password guessing
            raise Unauthorized("incorrect password")
        return json_response({"authenticated": True, "expires_in": auth.sessions.ttl},
                             cookies=[auth.cookie_for(auth.sessions.create())])

    @router.route("POST", "/api/logout", public=True)
    def logout(request):
        auth.sessions.destroy(auth.token_of(request))
        return json_response({"authenticated": False}, cookies=[auth.expired_cookie()])

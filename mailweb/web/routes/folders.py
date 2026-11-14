"""Folder list."""
from ..http import json_response


def register(router, ctx):
    @router.route("GET", "/api/folders")
    def folders(request):
        return json_response({"folders": ctx.mail_for(request).folders(refresh=request.flag("refresh"))})

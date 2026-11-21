"""Add, list, edit, cancel work for, and remove mail accounts."""
from ..http import json_response


EDITABLE = ("name", "host", "port", "user", "password", "tls", "tls_verify")


def register(router, ctx):
    registry = ctx.accounts

    @router.route("GET", "/api/accounts")
    def list_accounts(request):
        return json_response({"accounts": registry.list()})

    @router.route("POST", "/api/accounts")
    def add_account(request):
        return json_response({"account": registry.add(request.json())})

    @router.route("PATCH", "/api/accounts")
    def update_account(request):
        body = request.json()
        changes = {key: body[key] for key in EDITABLE if key in body}
        account, reconnected = registry.update(str(body.get("id", "")), changes)
        return json_response({"account": account, "reconnected": reconnected})

    @router.route("POST", "/api/accounts/cancel")
    def cancel_work(request):
        registry.cancel(request.required("account"))
        return json_response({"cancelled": True})

    @router.route("DELETE", "/api/accounts")
    def remove_account(request):
        registry.remove(request.required("id"))
        return json_response({"removed": True})

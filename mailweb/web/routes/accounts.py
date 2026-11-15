"""Add, list, rename and remove mail accounts."""
from ..http import json_response


def register(router, ctx):
    registry = ctx.accounts

    @router.route("GET", "/api/accounts")
    def list_accounts(request):
        return json_response({"accounts": registry.list()})

    @router.route("POST", "/api/accounts")
    def add_account(request):
        return json_response({"account": registry.add(request.json())})

    @router.route("PATCH", "/api/accounts")
    def rename_account(request):
        body = request.json()
        return json_response({"account": registry.rename(str(body.get("id", "")), body.get("name", ""))})

    @router.route("DELETE", "/api/accounts")
    def remove_account(request):
        registry.remove(request.required("id"))
        return json_response({"removed": True})

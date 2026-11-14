"""Message list, message view, body document, attachments and raw download."""
from ..http import file_response, html_response, json_response

# The body is untrusted HTML: no scripts, no network, no same-origin powers.
# Images from the internet are allowed only when the user asked for them (?images=1)
# or the operator enabled [mail] load_remote_images.
_CSP = ("default-src 'none'; img-src {images}; font-src data:; style-src 'unsafe-inline'; "
        "sandbox allow-popups allow-popups-to-escape-sandbox; frame-ancestors 'self'")


def _body_headers(allow_remote_images: bool) -> dict:
    return {"Content-Security-Policy": _CSP.format(images="data: http: https:" if allow_remote_images else "data:")}


def register(router, ctx):
    def target(request):
        """(MailService, folder, uid) for message-level endpoints."""
        return ctx.mail_for(request), request.required("folder"), request.int_param("uid")

    @router.route("GET", "/api/messages")
    def message_list(request):
        return json_response(ctx.mail_for(request).list_messages(
            folder=request.required("folder"), page=request.int_param("page", 1, minimum=1),
            query=request.param("q"), refresh=request.flag("refresh")))

    @router.route("GET", "/api/message")
    def message_detail(request):
        mail, folder, uid = target(request)
        return json_response(mail.detail(folder, uid))

    @router.route("GET", "/api/message/body")
    def message_body(request):
        mail, folder, uid = target(request)
        return html_response(mail.content(folder, uid).body_document(), _body_headers(request.flag("images") or mail.load_remote_images))

    @router.route("GET", "/api/message/attachment")
    def attachment(request):
        mail, folder, uid = target(request)
        found, data = mail.content(folder, uid).attachment(request.int_param("index"))
        return file_response(data, found.content_type, found.filename)

    @router.route("GET", "/api/message/raw")
    def raw(request):
        mail, folder, uid = target(request)
        return file_response(mail.content(folder, uid).raw, "message/rfc822", f"message-{uid}.eml")

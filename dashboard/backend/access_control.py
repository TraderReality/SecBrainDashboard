"""HTTP Basic access control for the LAN web application."""

import base64
import binascii
import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse


def auth_required() -> bool:
    setting = os.environ.get("SECBRAIN_AUTH_REQUIRED", "0")
    if setting not in {"0", "1"}:
        raise RuntimeError("SECBRAIN_AUTH_REQUIRED muss 0 oder 1 sein.")
    return setting == "1"


def validate_auth_configuration() -> None:
    if auth_required():
        username = os.environ.get("SECBRAIN_HTTP_USER", "")
        password = os.environ.get("SECBRAIN_HTTP_PASSWORD", "")
        if not username or not password or ":" in username:
            raise RuntimeError("HTTP-Zugangsdaten fehlen oder sind ungültig; Web-App startet nicht.")


def valid_basic_header(header: str, username: str, password: str) -> bool:
    if header[:6].lower() != "basic " or len(header) > 4096:
        return False
    try:
        decoded = base64.b64decode(header[6:], validate=True)
        supplied_user, separator, supplied_password = decoded.partition(b":")
    except (ValueError, binascii.Error):
        return False
    return bool(separator) and (
        secrets.compare_digest(supplied_user, username.encode("utf-8"))
        & secrets.compare_digest(supplied_password, password.encode("utf-8"))
    )


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path == "/healthz" or not auth_required():
            return await call_next(request)

        username = os.environ.get("SECBRAIN_HTTP_USER", "")
        password = os.environ.get("SECBRAIN_HTTP_PASSWORD", "")
        if not username or not password:
            return PlainTextResponse("Zugang nicht konfiguriert.", status_code=503)

        if valid_basic_header(request.headers.get("authorization", ""), username, password):
            return await call_next(request)

        return PlainTextResponse(
            "Anmeldung erforderlich.",
            status_code=401,
            headers={
                "WWW-Authenticate": 'Basic realm="SECBrain Watcher", charset="UTF-8"',
                "Cache-Control": "no-store",
            },
        )

"""HTTP client helpers. Respects HIVEMIND_SSL_VERIFY for corp/uni networks with SSL inspection."""

import os
from typing import Any


def format_retry_after(response: Any) -> str:
    """
    Read Retry-After from response headers and return a short message for the user.
    response: object with .headers (e.g. httpx.Response). Headers may be case-insensitive.
    Returns e.g. " Back off: retry after 60s" or " Back off: retry after <date>" or "".
    """
    if response is None:
        return ""
    headers = getattr(response, "headers", None)
    if headers is None:
        return ""
    try:
        raw = headers.get("retry-after")
    except Exception:
        raw = None
    if raw is None:
        return ""
    raw = str(raw).strip()
    if not raw:
        return ""
    # Integer seconds
    try:
        sec = int(raw)
        return f" Back off: retry after {sec}s"
    except ValueError:
        pass
    # HTTP-date or other
    return f" Back off: Retry-After {raw}"


def ssl_verify() -> bool:
    """
    Return False if HIVEMIND_SSL_VERIFY is 'false' or '0' (e.g. university/corp WiFi with MITM).
    Otherwise True. Use for httpx Client(verify=ssl_verify()).
    """
    v = os.environ.get("HIVEMIND_SSL_VERIFY", "true").strip().lower()
    return v not in ("false", "0", "no", "off")

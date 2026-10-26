"""Browser-facing protections: cross-site request checks, cookie flags, response headers."""
import os
from urllib.parse import urlparse

from fastapi import Request

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _env_list(*names: str):
    for name in names:
        raw = os.environ.get(name, "")
        if raw.strip():
            return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    return []


def allowed_origins():
    """Extra origins allowed to call the API (CORS + CSRF): SIPPTESTER_ALLOWED_ORIGINS."""
    return _env_list("SIPPTESTER_ALLOWED_ORIGINS")


def _trust_proxy() -> bool:
    return os.environ.get("SIPPTESTER_TRUST_PROXY") == "1"


def request_host(request: Request) -> str:
    """The host:port the browser used (X-Forwarded-Host only when the proxy is trusted)."""
    if _trust_proxy() and request.headers.get("x-forwarded-host"):
        return request.headers["x-forwarded-host"].split(",")[0].strip()
    return request.headers.get("host", "")


def cross_site_blocked(request: Request) -> bool:
    """
    True if this looks like a cross-site browser request that changes state.

    Browsers always attach Origin (or Sec-Fetch-Site) to cross-site POST/PUT/
    DELETE, so a mismatch is a CSRF attempt. Requests with neither header come
    from scripts/curl, which CSRF cannot use (it needs the victim's browser).
    """
    if request.method in _SAFE_METHODS:
        return False
    origin = request.headers.get("origin")
    if origin:
        if origin.rstrip("/") in allowed_origins():
            return False
        return urlparse(origin).netloc != request_host(request)
    site = request.headers.get("sec-fetch-site")
    if site:
        return site not in ("same-origin", "none")
    referer = request.headers.get("referer")
    if referer:
        return urlparse(referer).netloc != request_host(request)
    return False


def cookie_secure(request: Request) -> bool:
    """
    Secure flag for the session cookie. Force with SIPPTESTER_COOKIE_SECURE=1 (or 0);
    otherwise on when the request is HTTPS, or when a trusted proxy says it was
    (SIPPTESTER_TRUST_PROXY=1 and X-Forwarded-Proto: https).
    """
    forced = os.environ.get("SIPPTESTER_COOKIE_SECURE")
    if forced in ("0", "1"):
        return forced == "1"
    if request.url.scheme == "https":
        return True
    return _trust_proxy() and request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    # The UI uses inline handlers, so scripts must allow 'unsafe-inline'; the rest of
    # the policy still blocks plugins, <base> hijacking, framing and foreign form posts.
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'self'"
    ),
}

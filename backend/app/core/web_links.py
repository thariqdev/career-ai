"""The one rule for user-supplied links the frontend renders as <a href>."""

from urllib.parse import urlparse

from app.core.exceptions import InvalidResourceUrlError


def require_web_link(url: str) -> str:
    """Return the stripped URL if it's http(s) with a host; else InvalidResourceUrlError (422).

    Only allowing http(s) is also what keeps values like "javascript:..." out of links.
    """
    clean = url.strip()
    parsed = urlparse(clean)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        raise InvalidResourceUrlError(clean)
    return clean

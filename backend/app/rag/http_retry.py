"""Retry with backoff for hosted AI APIs (production providers).

Free tiers answer 429 ("too many requests") when a per-minute budget is used up, and
any hosted API has the odd 5xx or timeout. Those are worth a few patient retries; any
other answer (400 bad request, 401 wrong key...) is final and fails at once.

Waits double each time (1 s, 2 s, 4 s, 8 s) unless the server says how long to wait
(Retry-After, in seconds), capped so one request never hangs the assistant for long.
"""

import time
from collections.abc import Callable

import httpx

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES = 4
MAX_WAIT_SECONDS = 20.0


def retry_wait(response: httpx.Response | None, attempt: int) -> float:
    """Seconds to wait before retry number `attempt` (0-based)."""
    if response is not None:
        try:
            return min(float(response.headers.get("retry-after", "")), MAX_WAIT_SECONDS)
        except ValueError:
            pass  # missing or an HTTP date: fall back to doubling
    return min(2.0**attempt, MAX_WAIT_SECONDS)


def post_with_retry(
    client: httpx.Client,
    url: str,
    *,
    json: dict,
    headers: dict[str, str],
    max_retries: int = MAX_RETRIES,
    sleep: Callable[[float], None] = time.sleep,  # tests pass a fake
) -> httpx.Response:
    """POST, retrying 429 / 5xx / network errors. Returns the last response; raises the
    last httpx error if every attempt failed to connect."""
    for attempt in range(max_retries + 1):
        try:
            response = client.post(url, json=json, headers=headers)
        except httpx.TransportError:
            if attempt == max_retries:
                raise
            sleep(retry_wait(None, attempt))
            continue
        if response.status_code not in RETRY_STATUSES or attempt == max_retries:
            return response
        sleep(retry_wait(response, attempt))
    raise AssertionError("unreachable")

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

CONTACT_LIMIT = 5
CONTACT_WINDOW_SECONDS = 3600

# ponytail: per-process memory. Resets on restart and is wrong the moment a second
# uvicorn worker exists (start.sh runs one on purpose); then move it to a shared store.
_hits: dict[str, deque[float]] = defaultdict(deque)


def client_ip(request: Request) -> str:
    # Leftmost X-Forwarded-For, not uvicorn --forwarded-allow-ips: Caddy overwrites a
    # client-sent XFF and the backend port is unpublished, so only Caddy sets it.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def hit_contact_limit(request: Request) -> None:
    """Record one accepted message for this IP; 429 if it is past the hourly cap."""
    ip = client_ip(request)
    now = time.monotonic()
    hits = _hits[ip]
    while hits and now - hits[0] >= CONTACT_WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= CONTACT_LIMIT:
        retry = int(CONTACT_WINDOW_SECONDS - (now - hits[0])) + 1
        raise HTTPException(
            status_code=429,
            detail="Too many messages. Try again later.",
            headers={"Retry-After": str(retry)},
        )
    hits.append(now)

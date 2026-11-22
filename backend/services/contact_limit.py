import ipaddress
import time
from collections import defaultdict, deque

from fastapi import Request

from errors import ErrorCode, raise_coded

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


def _bucket(ip: str) -> str:
    # A v6 client owns a whole /64; per-address keys would let it rotate past the cap.
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if addr.version == 6:
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return ip


def hit_contact_limit(request: Request) -> None:
    """Record one accepted message for this IP; 429 if it is past the hourly cap."""
    ip = _bucket(client_ip(request))
    now = time.monotonic()
    # ponytail: O(keys) sweep per hit; fine at contact-form volume.
    for key, stamps in list(_hits.items()):
        if not stamps or now - stamps[-1] >= CONTACT_WINDOW_SECONDS:
            del _hits[key]
    hits = _hits[ip]
    while hits and now - hits[0] >= CONTACT_WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= CONTACT_LIMIT:
        retry = int(CONTACT_WINDOW_SECONDS - (now - hits[0])) + 1
        raise_coded(
            429,
            ErrorCode.contact_rate_limited,
            "Too many messages. Try again later.",
            headers={"Retry-After": str(retry)},
        )
    hits.append(now)

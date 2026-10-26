"""HTTP caching for API responses.

The snapshot is immutable for the life of a deployment, so successful GETs can be cached by
the CDN (Vercel's edge cache is scoped per deployment, so a redeploy with new data is never
served stale answers). Most traffic then never reaches the Python function, which keeps cold
starts off the user path. Errors and health checks are never cached.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response

CACHEABLE = "public, max-age=300, s-maxage=86400, stale-while-revalidate=604800"
NOT_CACHEABLE = "no-store"
UNCACHED_PATHS = frozenset({"/api/health"})


async def cache_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    cacheable = (
        request.method == "GET"
        and response.status_code == 200
        and request.url.path not in UNCACHED_PATHS
    )
    response.headers.setdefault("Cache-Control", CACHEABLE if cacheable else NOT_CACHEABLE)
    return response

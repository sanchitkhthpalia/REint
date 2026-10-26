"""Structured (JSON lines) logging and per-request access logs."""

from __future__ import annotations

import json
import logging
import re
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger("app")

# Container healthchecks hit this every few seconds; keep them out of INFO logs.
QUIET_PATHS = frozenset({"/api/health"})
# Client-supplied ids end up in logs and headers, so only accept short, plain ones.
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Structured fields go in `extra={"fields": {...}}`."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def _request_id(request: Request) -> str:
    """Reuse a well-formed incoming id (e.g. from nginx); otherwise mint one."""
    incoming = request.headers.get("x-request-id", "")
    return incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else uuid.uuid4().hex


async def access_log(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Log every request, including ones that crash, and turn crashes into JSON 500s."""
    request_id = _request_id(request)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "unhandled error",
            extra={"fields": {"request_id": request_id, "path": request.url.path}},
        )
        response = JSONResponse(
            {"detail": "Internal server error", "request_id": request_id},
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )
    response.headers["X-Request-ID"] = request_id
    level = logging.DEBUG if request.url.path in QUIET_PATHS else logging.INFO
    logger.log(
        level,
        "request",
        extra={
            "fields": {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query": str(request.url.query),
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        },
    )
    return response

"""HTTP middleware: request id, security headers, path normalization, metrics."""

from __future__ import annotations

import re
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings
from app.observability.metrics import HTTP_REQUESTS, HTTP_REQUEST_DURATION

# Collapse UUIDs / numeric ids so Prometheus label cardinality stays bounded
# (classic big-tech SRE rule: never put raw path params into metric labels).
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_NUM_RE = re.compile(r"/\d+")


def normalize_path(path: str) -> str:
    path = _UUID_RE.sub("{id}", path)
    path = _NUM_RE.sub("/{id}", path)
    # Cap path length to avoid abuse
    if len(path) > 120:
        return path[:120]
    return path


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        settings = get_settings()
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=normalize_path(request.url.path),
            method=request.method,
        )

        # Reject oversized bodies early (defense in depth for public ingest APIs).
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit():
            if int(content_length) > settings.max_request_body_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "payload_too_large",
                            "message": "Request body too large",
                            "request_id": request_id,
                        }
                    },
                    headers={"X-Request-ID": request_id},
                )

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            # Baseline security headers (API-focused subset of big-tech defaults).
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Referrer-Policy", "no-referrer")
            response.headers.setdefault(
                "Cache-Control", "no-store" if request.url.path.startswith("/api") else "no-cache"
            )
            return response
        finally:
            elapsed = time.perf_counter() - start
            path_template = normalize_path(request.url.path)
            HTTP_REQUESTS.labels(
                method=request.method,
                path=path_template,
                status=str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION.labels(
                method=request.method,
                path=path_template,
            ).observe(elapsed)

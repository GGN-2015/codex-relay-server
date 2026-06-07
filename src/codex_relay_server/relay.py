from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from .auth import resolve_authorization_header
from .config import Settings

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

REQUEST_HEADERS_TO_DROP = HOP_BY_HOP_HEADERS | {
    "host",
    "content-length",
}

RESPONSE_HEADERS_TO_DROP = HOP_BY_HOP_HEADERS

ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


def create_app(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.relay.timeout_seconds),
        verify=settings.relay.verify_ssl,
        transport=transport,
        follow_redirects=False,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await client.aclose()

    app = FastAPI(
        title="Codex Relay Server",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.http_client = client

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.api_route("/{path:path}", methods=ALL_METHODS, response_model=None)
    async def relay_request(path: str, request: Request) -> Response:
        try:
            return await forward_request(request, path, settings, client)
        except HTTPException:
            raise
        except httpx.TimeoutException:
            return JSONResponse({"detail": "Upstream request timed out."}, status_code=504)
        except httpx.TransportError as exc:
            return JSONResponse({"detail": f"Upstream request failed: {exc.__class__.__name__}"}, status_code=502)

    return app


async def forward_request(
    request: Request,
    incoming_path: str,
    settings: Settings,
    client: httpx.AsyncClient,
) -> Response:
    target_url = build_upstream_url(
        settings.relay.upstream_url,
        incoming_path,
        request.url.query,
        settings.relay.local_base_path,
        settings.relay.strip_local_base_path,
    )
    headers = build_upstream_headers(request.headers.items(), settings)
    body = await request.body()

    upstream_request = client.build_request(
        request.method,
        target_url,
        headers=headers,
        content=body,
    )
    upstream_response = await client.send(upstream_request, stream=True)
    response_headers = filter_response_headers(upstream_response.headers.items())

    if upstream_response.is_stream_consumed:
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=response_headers,
            media_type=upstream_response.headers.get("content-type"),
        )

    return StreamingResponse(
        upstream_response.aiter_raw(),
        status_code=upstream_response.status_code,
        headers=response_headers,
        background=BackgroundTask(upstream_response.aclose),
    )


def build_upstream_url(
    upstream_url: str,
    incoming_path: str,
    query_string: str | bytes,
    local_base_path: str,
    strip_local_base_path: bool,
) -> str:
    suffix = incoming_path.strip("/")

    validate_local_path(incoming_path, local_base_path)

    if strip_local_base_path and local_base_path:
        normalized_path = f"/{suffix}" if suffix else "/"
        prefix = local_base_path.rstrip("/")
        if normalized_path == prefix:
            suffix = ""
        elif normalized_path.startswith(f"{prefix}/"):
            suffix = normalized_path[len(prefix) :].lstrip("/")

    target = upstream_url.rstrip("/")
    if suffix:
        target = f"{target}/{suffix}"

    if query_string:
        query = query_string.decode("utf-8") if isinstance(query_string, bytes) else query_string
        target = f"{target}?{query}"

    return target


def validate_local_path(incoming_path: str, local_base_path: str) -> None:
    if not local_base_path:
        return

    normalized_path = f"/{incoming_path.strip('/')}" if incoming_path.strip("/") else "/"
    prefix = local_base_path.rstrip("/")
    if normalized_path == prefix or normalized_path.startswith(f"{prefix}/"):
        return

    raise HTTPException(status_code=404, detail="This path is outside the configured local base path.")


def build_upstream_headers(incoming_headers: Iterable[tuple[str, str]], settings: Settings) -> dict[str, str]:
    headers = {
        key: value
        for key, value in incoming_headers
        if key.lower() not in REQUEST_HEADERS_TO_DROP
    }

    authorization = resolve_authorization_header(headers.get("authorization"), settings.auth)
    headers.pop("authorization", None)
    if authorization:
        headers["authorization"] = authorization

    return headers


def filter_response_headers(incoming_headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    return {
        key: value
        for key, value in incoming_headers
        if key.lower() not in RESPONSE_HEADERS_TO_DROP
    }

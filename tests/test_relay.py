from __future__ import annotations

import httpx
import pytest

from codex_relay_server.config import Settings
from codex_relay_server.relay import build_upstream_url, create_app


async def request_relay(app, method: str, url: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://relay.test",
    ) as client:
        response = await client.request(method, url, **kwargs)
    await app.state.http_client.aclose()
    return response


def test_build_upstream_url_strips_configured_local_base_path() -> None:
    assert (
        build_upstream_url(
            "https://upstream.example/custom-api",
            "v1/responses",
            "stream=true",
            "/v1",
            True,
        )
        == "https://upstream.example/custom-api/responses?stream=true"
    )


def test_build_upstream_url_can_forward_without_stripping() -> None:
    assert (
        build_upstream_url(
            "https://upstream.example/root",
            "v1/models",
            "",
            "/v1",
            False,
        )
        == "https://upstream.example/root/v1/models"
    )


def test_root_local_base_path_accepts_any_path_by_default() -> None:
    assert (
        build_upstream_url(
            "https://upstream.example/api",
            "responses",
            "",
            "/",
            True,
        )
        == "https://upstream.example/api/responses"
    )


@pytest.mark.asyncio
async def test_direct_mode_forwards_path_query_body_and_authorization() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = await request.aread()
        return httpx.Response(200, json={"ok": True}, headers={"x-upstream": "yes"})

    settings = Settings.model_validate(
        {
            "relay": {
                "upstream_url": "https://upstream.example/custom-root",
                "local_base_path": "/v1",
                "strip_local_base_path": True,
            },
            "auth": {"mode": "direct"},
        }
    )
    app = create_app(settings, transport=httpx.MockTransport(handler))

    response = await request_relay(
        app,
        "POST",
        "/v1/chat/completions?debug=1",
        headers={"authorization": "Bearer client-key"},
        json={"model": "demo"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert response.headers["x-upstream"] == "yes"
    assert captured == {
        "url": "https://upstream.example/custom-root/chat/completions?debug=1",
        "auth": "Bearer client-key",
        "body": b'{"model":"demo"}',
    }


@pytest.mark.asyncio
async def test_custom_local_base_path_forwards_responses_endpoint() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = await request.aread()
        return httpx.Response(200, json={"id": "resp_mock"})

    settings = Settings.model_validate(
        {
            "relay": {
                "upstream_url": "https://upstream.example/not-v1",
                "local_base_path": "/openai",
                "strip_local_base_path": True,
            },
            "auth": {"mode": "direct"},
        }
    )
    app = create_app(settings, transport=httpx.MockTransport(handler))

    response = await request_relay(
        app,
        "POST",
        "/openai/responses?stream=true",
        headers={"authorization": "Bearer client-key"},
        json={"model": "demo", "input": "hello"},
    )

    assert response.status_code == 200
    assert response.json() == {"id": "resp_mock"}
    assert captured == {
        "url": "https://upstream.example/not-v1/responses?stream=true",
        "body": b'{"model":"demo","input":"hello"}',
    }


@pytest.mark.asyncio
async def test_configured_local_base_path_is_enforced() -> None:
    called = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    settings = Settings.model_validate(
        {
            "relay": {
                "upstream_url": "https://upstream.example/v1",
                "local_base_path": "/openai",
            },
            "auth": {"mode": "direct"},
        }
    )
    app = create_app(settings, transport=httpx.MockTransport(handler))

    response = await request_relay(
        app,
        "GET",
        "/v1/models",
        headers={"authorization": "Bearer client-key"},
    )

    assert response.status_code == 404
    assert called is False


@pytest.mark.asyncio
async def test_transform_mode_maps_client_key_to_upstream_key() -> None:
    captured: dict[str, str | None] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"ok": True})

    settings = Settings.model_validate(
        {
            "relay": {"upstream_url": "https://upstream.example/v1"},
            "auth": {
                "mode": "transform",
                "key_map": {"client-a": "upstream-a"},
                "default_key": "default-upstream",
            },
        }
    )
    app = create_app(settings, transport=httpx.MockTransport(handler))

    response = await request_relay(
        app,
        "GET",
        "/v1/models",
        headers={"authorization": "Bearer client-a"},
    )

    assert response.status_code == 200
    assert captured["auth"] == "Bearer upstream-a"


@pytest.mark.asyncio
async def test_transform_mode_uses_default_key_for_unknown_client_key() -> None:
    captured: dict[str, str | None] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"ok": True})

    settings = Settings.model_validate(
        {
            "relay": {"upstream_url": "https://upstream.example/v1"},
            "auth": {
                "mode": "transform",
                "key_map": {"client-a": "upstream-a"},
                "default_key": "default-upstream",
            },
        }
    )
    app = create_app(settings, transport=httpx.MockTransport(handler))

    response = await request_relay(
        app,
        "GET",
        "/v1/models",
        headers={"authorization": "Bearer client-b"},
    )

    assert response.status_code == 200
    assert captured["auth"] == "Bearer default-upstream"


@pytest.mark.asyncio
async def test_transform_mode_rejects_when_no_mapping_or_default_exists() -> None:
    called = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    settings = Settings.model_validate(
        {
            "relay": {"upstream_url": "https://upstream.example/v1"},
            "auth": {"mode": "transform", "key_map": {}},
        }
    )
    app = create_app(settings, transport=httpx.MockTransport(handler))

    response = await request_relay(
        app,
        "GET",
        "/v1/models",
        headers={"authorization": "Bearer client-b"},
    )

    assert response.status_code == 401
    assert called is False

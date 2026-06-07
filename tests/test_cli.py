from __future__ import annotations

import asyncio

import uvicorn

from codex_relay_server.cli import build_default_access_endpoint, main
from codex_relay_server.config import Settings


def test_build_default_access_endpoint_uses_loopback_for_wildcard_host() -> None:
    settings = Settings.model_validate(
        {
            "server": {"host": "0.0.0.0", "port": 9000},
            "relay": {"local_base_path": "/openai"},
        }
    )

    assert build_default_access_endpoint(settings) == "http://127.0.0.1:9000/openai"


def test_build_default_access_endpoint_omits_root_base_path() -> None:
    settings = Settings.model_validate(
        {
            "server": {"host": "127.0.0.1", "port": 8000},
            "relay": {"local_base_path": "/"},
        }
    )

    assert build_default_access_endpoint(settings) == "http://127.0.0.1:8000"


def test_build_default_access_endpoint_wraps_ipv6_host() -> None:
    settings = Settings.model_validate(
        {
            "server": {"host": "::1", "port": 8000},
            "relay": {"local_base_path": "/v1"},
        }
    )

    assert build_default_access_endpoint(settings) == "http://[::1]:8000/v1"


def test_main_prints_default_access_endpoint(monkeypatch, capsys) -> None:
    run_kwargs = {}

    def fake_run(app, **kwargs) -> None:
        run_kwargs.update(kwargs)
        asyncio.run(app.state.http_client.aclose())

    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "codex-relay-server",
            "--host",
            "0.0.0.0",
            "--port",
            "9100",
            "--local-base-path",
            "/openai",
        ],
    )

    main()

    assert capsys.readouterr().out == "Default access endpoint: http://127.0.0.1:9100/openai\n"
    assert run_kwargs == {"host": "0.0.0.0", "port": 9100, "log_level": "info"}

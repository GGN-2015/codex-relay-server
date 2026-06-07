from __future__ import annotations

import json

from codex_relay_server import Settings, load_settings


def test_load_settings_from_json_file(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "server": {"host": "0.0.0.0", "port": 9000},
                "relay": {"upstream_url": "https://upstream.example/custom", "local_base_path": "/openai"},
                "auth": {"mode": "direct"},
            }
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.server.host == "0.0.0.0"
    assert settings.server.port == 9000
    assert settings.relay.upstream_url == "https://upstream.example/custom"
    assert settings.relay.local_base_path == "/openai"


def test_load_settings_from_mapping() -> None:
    settings = load_settings(
        {
            "relay": {
                "upstream_url": "https://upstream.example/root/",
                "local_base_path": "api",
            },
            "auth": {"mode": "transform", "key_map": {"client": "upstream"}},
        }
    )

    assert settings.relay.upstream_url == "https://upstream.example/root"
    assert settings.relay.local_base_path == "/api"
    assert settings.auth.key_map["client"].get_secret_value() == "upstream"


def test_load_settings_accepts_existing_settings() -> None:
    original = Settings.model_validate({"relay": {"upstream_url": "https://upstream.example/v1"}})

    loaded = load_settings(original)

    assert loaded == original


def test_default_local_base_path_is_root() -> None:
    settings = load_settings({"relay": {"upstream_url": "https://config.example/api"}})

    assert settings.relay.local_base_path == "/"


def test_empty_local_base_path_is_normalized_to_root() -> None:
    settings = load_settings(
        {
            "relay": {
                "upstream_url": "https://config.example/api",
                "local_base_path": "",
            }
        }
    )

    assert settings.relay.upstream_url == "https://config.example/api"
    assert settings.relay.local_base_path == "/"

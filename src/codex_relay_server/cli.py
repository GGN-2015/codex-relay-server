from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import uvicorn

from .config import Settings, load_settings
from .relay import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a LAN OpenAI-compatible relay server.")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to a JSON config file.",
    )
    parser.add_argument("--host", help="Override server.host, for example 0.0.0.0 or a LAN IP.")
    parser.add_argument("--port", type=int, help="Override server.port.")
    parser.add_argument("--upstream-url", help="Override relay.upstream_url.")
    parser.add_argument("--local-base-path", help="Override relay.local_base_path.")
    parser.add_argument(
        "--strip-local-base-path",
        type=parse_bool,
        help="Override relay.strip_local_base_path with true or false.",
    )
    parser.add_argument("--auth-mode", choices=("direct", "transform"), help="Override auth.mode.")
    parser.add_argument("--log-level", help="Override server.log_level.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    settings = load_settings(args.config)
    updates = {}
    if args.host is not None:
        updates.setdefault("server", {})["host"] = args.host
    if args.port is not None:
        updates.setdefault("server", {})["port"] = args.port
    if args.log_level is not None:
        updates.setdefault("server", {})["log_level"] = args.log_level
    if args.upstream_url is not None:
        updates.setdefault("relay", {})["upstream_url"] = args.upstream_url
    if args.local_base_path is not None:
        updates.setdefault("relay", {})["local_base_path"] = args.local_base_path
    if args.strip_local_base_path is not None:
        updates.setdefault("relay", {})["strip_local_base_path"] = args.strip_local_base_path
    if args.auth_mode is not None:
        updates.setdefault("auth", {})["mode"] = args.auth_mode
    if updates:
        settings = type(settings).model_validate(_deep_update(settings.model_dump(mode="python"), updates))

    app = create_app(settings)
    print(f"Default access endpoint: {build_default_access_endpoint(settings)}", flush=True)
    uvicorn.run(app, host=settings.server.host, port=settings.server.port, log_level=settings.server.log_level)


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value!r}")


def _deep_update(original: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(original.get(key), dict):
            original[key] = _deep_update(original[key], value)
        else:
            original[key] = value
    return original


def build_default_access_endpoint(settings: Settings) -> str:
    host = settings.server.host.strip()
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    elif ":" in host and not host.startswith("["):
        host = f"[{host}]"

    endpoint = f"http://{host}:{settings.server.port}"
    if settings.relay.local_base_path != "/":
        endpoint = f"{endpoint}{settings.relay.local_base_path}"
    return endpoint

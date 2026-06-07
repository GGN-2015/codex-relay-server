from __future__ import annotations

from copy import deepcopy
import json
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator


class AuthMode(StrEnum):
    DIRECT = "direct"
    TRANSFORM = "transform"


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"

    @field_validator("port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return value


class RelayConfig(BaseModel):
    upstream_url: str = "https://api.openai.com/v1"
    local_base_path: str = "/"
    strip_local_base_path: bool = True
    timeout_seconds: float = 300
    verify_ssl: bool = True

    @model_validator(mode="before")
    @classmethod
    def migrate_old_base_path_names(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "local_base_path" not in data and "public_base_path" in data:
                data["local_base_path"] = data["public_base_path"]
            if "strip_local_base_path" not in data and "strip_public_base_path" in data:
                data["strip_local_base_path"] = data["strip_public_base_path"]
        return data

    @field_validator("upstream_url")
    @classmethod
    def validate_upstream_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("upstream_url is required")
        if not value.startswith(("http://", "https://")):
            raise ValueError("upstream_url must start with http:// or https://")
        return value.rstrip("/")

    @field_validator("local_base_path")
    @classmethod
    def validate_local_base_path(cls, value: str) -> str:
        value = value.strip()
        if value in {"", "/"}:
            return "/"
        if not value.startswith("/"):
            value = f"/{value}"
        return value.rstrip("/")

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        return value


class AuthConfig(BaseModel):
    mode: AuthMode = AuthMode.DIRECT
    key_map: dict[str, SecretStr] = Field(default_factory=dict)
    default_key: SecretStr | None = None


class Settings(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    relay: RelayConfig = Field(default_factory=RelayConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)


ConfigInput = Settings | Mapping[str, Any] | str | Path | None


def load_settings(config: ConfigInput = None) -> Settings:
    raw: dict[str, Any] = {}
    if isinstance(config, Settings):
        raw = config.model_dump(mode="python")
    elif isinstance(config, Mapping):
        raw = deepcopy(dict(config))
    elif config:
        path = Path(config)
        if not path.exists():
            raise FileNotFoundError(f"config file not found: {path}")
        with path.open("r", encoding="utf-8") as file:
            loaded = json.load(file)
        if not isinstance(loaded, dict):
            raise ValueError("config file must contain a JSON object")
        raw = loaded

    return Settings.model_validate(raw)

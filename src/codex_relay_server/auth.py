from __future__ import annotations

from fastapi import HTTPException, status

from .config import AuthConfig, AuthMode


def resolve_authorization_header(incoming_authorization: str | None, config: AuthConfig) -> str | None:
    if config.mode == AuthMode.DIRECT:
        return incoming_authorization

    client_key = extract_client_key(incoming_authorization)
    upstream_secret = config.key_map.get(client_key or "") if client_key else None
    if upstream_secret is None:
        upstream_secret = config.default_key

    if upstream_secret is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No upstream API key is available for this client key.",
        )

    return f"Bearer {upstream_secret.get_secret_value()}"


def extract_client_key(authorization_header: str | None) -> str | None:
    if authorization_header is None:
        return None

    authorization_header = authorization_header.strip()
    if not authorization_header:
        return None

    scheme, separator, value = authorization_header.partition(" ")
    if separator and scheme.lower() == "bearer":
        value = value.strip()
        return value or None

    return authorization_header

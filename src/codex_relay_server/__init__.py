"""OpenAI-compatible LAN relay server."""

from .config import AuthConfig, AuthMode, RelayConfig, ServerConfig, Settings, load_settings
from .relay import create_app

__version__ = "0.1.0"

__all__ = [
    "AuthConfig",
    "AuthMode",
    "RelayConfig",
    "ServerConfig",
    "Settings",
    "__version__",
    "create_app",
    "load_settings",
]

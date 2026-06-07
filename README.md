# codex-relay-server

A LAN relay server for OpenAI-compatible HTTP APIs.

Use this when one computer can reach the upstream model provider, but other computers on the LAN can only reach that computer. LAN clients point their OpenAI SDKs at this relay; the relay forwards requests to your configured upstream API root and streams the upstream response back.

## Features

- Bind to any local IP and port, such as `0.0.0.0:8000` or a specific LAN adapter IP.
- Use any upstream API root URL. The upstream does not need to use `/v1`.
- Configure the local client-facing base path, such as `/`, `/v1`, `/openai`, or `/api/openai`.
- Forward all endpoints with the same path rules, including `/chat/completions`, `/responses`, `/models`, and future API paths.
- Pass through normal JSON responses and streaming SSE responses.
- Support two API key modes:
  - `direct`: forward the incoming `Authorization` header unchanged.
  - `transform`: map client-visible keys to upstream keys, with an optional default upstream key.

## Installation

```powershell
.\venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Configuration

Copy the example config:

```powershell
Copy-Item config.example.json config.json
```

Edit `config.json`:

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8000
  },
  "relay": {
    "upstream_url": "https://your-upstream.example/custom-api",
    "local_base_path": "/",
    "strip_local_base_path": true
  },
  "auth": {
    "mode": "direct"
  }
}
```

With that config, an incoming LAN request to `/responses` is forwarded to:

```text
https://your-upstream.example/custom-api/responses
```

The default `local_base_path` is `/`, so the relay accepts requests from the root path. Set `local_base_path` explicitly if you want clients to use a specific base URL such as `/v1` or `/openai`.

Set `strip_local_base_path` to `false` if you want the full local path appended to the upstream URL.

You can expose any local base path:

```json
{
  "relay": {
    "upstream_url": "https://your-upstream.example/not-v1",
    "local_base_path": "/openai",
    "strip_local_base_path": true
  }
}
```

LAN clients can then use this base URL:

```text
http://<relay-lan-ip>:8000/openai
```

### Transform Mode

```json
{
  "auth": {
    "mode": "transform",
    "key_map": {
      "client-visible-key-a": "real-upstream-key-a",
      "client-visible-key-b": "real-upstream-key-b"
    },
    "default_key": "real-default-upstream-key"
  }
}
```

In transform mode, if the client sends:

```text
Authorization: Bearer client-visible-key-a
```

The upstream receives:

```text
Authorization: Bearer real-upstream-key-a
```

If the client key is not in `key_map` and `default_key` is configured, the relay uses `default_key`. If no default key is available, the relay returns `401`.

Keep real upstream keys in local `config.json` or Python-provided configuration. Do not commit them. This repository ignores `config.json`, `*.local.json`, and `*.secrets.json`.

### Python Configuration

You can also provide configuration from Python code instead of a JSON file:

```python
from codex_relay_server import create_app, load_settings

settings = load_settings(
    {
        "server": {"host": "0.0.0.0", "port": 8000},
        "relay": {
            "upstream_url": "https://your-upstream.example/custom-api",
            "local_base_path": "/openai",
            "strip_local_base_path": True,
        },
        "auth": {"mode": "direct"},
    }
)

app = create_app(settings)
```

## Run

```powershell
.\venv\Scripts\python.exe -m codex_relay_server --config config.json
```

You can temporarily override the bind address, port, upstream URL, and local base path:

```powershell
.\venv\Scripts\python.exe -m codex_relay_server `
  --config config.json `
  --host 0.0.0.0 `
  --port 8000 `
  --upstream-url https://your-upstream.example/custom-api `
  --local-base-path /openai
```

LAN client settings:

```text
base_url = http://<relay-lan-ip>:8000/<your-local-base-path>
api_key = <client-key>
```

## Tests

```powershell
.\venv\Scripts\python.exe -m pytest
```

Tests use a local mock upstream and do not need a real API key.

## Security Notes

- Do not expose this service to the public internet, especially in `transform` mode with `default_key` enabled.
- If you bind to `0.0.0.0`, make sure your firewall only allows trusted LAN clients.
- The project does not store private keys in tracked files. Put real keys in ignored local config files or Python-provided configuration.

# local-idp

A mock identity provider for local development and testing. It implements
OAuth2 and OpenID Connect flows so your app can authenticate without depending
on a real provider.

## Supported flows

| Flow | Grant type | Use case |
| ---- | ---------- | -------- |
| [Authorization Code](oauth2.md) | `authorization_code` | Browser-based login |
| [OpenID Connect](openid-connect.md) | `authorization_code` + `scope=openid` | Browser-based login with identity |
| [Client Credentials](client-credentials.md) | `client_credentials` | Machine-to-machine auth |
| [Token Exchange](token-exchange.md) | `urn:ietf:params:oauth:grant-type:token-exchange` | API key to short-lived JWT |
| [Simple Login](simple-login.md) | None (non-standard) | Quick token for tests and scripts |

## Quick start

```bash
uv run uvicorn app.main:app --port 9001 --reload
```

Discovery endpoint: [http://localhost:9001/.well-known/openid-configuration](http://localhost:9001/.well-known/openid-configuration)

See [Getting Started](getting-started.md) for setup details,
[Configuration](configuration.md) for environment variables, and
[Users & Clients](users-and-clients.md) for managing test personas.

## Building these docs

```bash
uv sync --group docs
uv run mkdocs serve
```

# Getting Started

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Install and run

```bash
git clone https://github.com/kmjbyrne/local-idp.git
cd local-idp
uv sync
uv run uvicorn app.main:app --port 9001 --reload
```

The server starts at [http://localhost:9001](http://localhost:9001).

## What you get on first run

On first startup, local-idp seeds an `instance/` directory with:

- **9 test users** with different roles and permissions
- **1 OAuth2 client** (`dev-client` / `dev-secret`)
- **1 signing key** (ES256 by default)

These files persist between restarts. Delete `instance/` to reset to defaults.

## Endpoints at a glance

| URL | What it is |
| --- | ---------- |
| [localhost:9001](http://localhost:9001) | Admin UI for managing users and clients |
| [localhost:9001/.well-known/openid-configuration](http://localhost:9001/.well-known/openid-configuration) | OIDC discovery document |
| [localhost:9001/.well-known/jwks.json](http://localhost:9001/.well-known/jwks.json) | Public signing keys |
| [localhost:9001/dev/authorize](http://localhost:9001/dev/authorize) | Authorization endpoint (sign-in page) |
| [localhost:9001/dev/token](http://localhost:9001/dev/token) | Token endpoint |
| [localhost:9001/dev/userinfo](http://localhost:9001/dev/userinfo) | Userinfo endpoint (Bearer token required) |
| localhost:9001/api/* | JSON API for managing users, clients, and keys |

## Connecting a client app

Point your app's OIDC/OAuth2 configuration at local-idp:

| Setting | Value |
| ------- | ----- |
| Issuer | `http://localhost:9001` |
| Client ID | `dev-client` |
| Client Secret | `dev-secret` |
| Redirect URI | Your app's callback URL (e.g. `http://localhost:3000/auth/callback`) |

The discovery document at `/.well-known/openid-configuration` provides the
rest. Most OAuth2/OIDC client libraries read it automatically.

## Signing in

When your app redirects to `/dev/authorize`, local-idp shows a sign-in page
listing all configured users. Click a name to sign in as that user. No
passwords.

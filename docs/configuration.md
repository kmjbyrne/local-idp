# Configuration

All settings are environment variables. They can also be set in `.env`,
`.env.local`, or `.env.{ENVIRONMENT}` files. Real environment variables take
precedence over files.

## Settings

| Variable | Type | Default | Purpose |
| -------- | ---- | ------- | ------- |
| `ENVIRONMENT` | string | `development` | Selects which `.env.{ENVIRONMENT}` file to load |
| `PROJECT_NAME` | string | `Mock IdP` | FastAPI app title |
| `VERSION` | string | `26.9.0` | Shown in `/docs` |
| `ISSUER` | string | `http://localhost:9000` | Token `iss` claim and base URL for discovery |
| `AUDIENCE` | string | `dev` | Token `aud` claim |
| `INSTANCE_DIR` | path | `instance/` | Where users.json, clients.json, and keys.json live |
| `TOKEN_LIFETIME` | int | `3600` | Access token expiry in seconds |
| `CORS_ORIGINS` | list | `["http://localhost:3000", "https://127.0.0.1.nip.io"]` | Allowed CORS origins |
| `LOG_LEVEL` | string | `INFO` | Python log level |
| `LOG_JSON` | bool | `false` | JSON-formatted log output |

## Env file cascade

Files are loaded in this order. Later files override earlier ones:

1. `.env`
2. `.env.local`
3. `.env.{ENVIRONMENT}`

Environment variables set in the shell override all files.

## Instance directory

The `INSTANCE_DIR` holds three JSON files:

| File | Contents |
| ---- | -------- |
| `users.json` | Array of user records |
| `clients.json` | Array of OAuth2 client registrations |
| `keys.json` | Signing keys (private + public) |

These files are read from disk on every request (no in-memory cache). Edits
via the admin UI or API take effect immediately.

Delete the directory to reset to seed data on next startup.

## ISSUER

The `ISSUER` value appears in:

- The `iss` claim of every token
- The discovery document at `/.well-known/openid-configuration`
- All endpoint URLs in the discovery document

If your app runs on a different host or port, set `ISSUER` to match. The
discovery document builds all endpoint URLs from this value.

# Local IdP

An identity provider for local development, with an editable user list.

> [!WARNING] This is a test fixture. It signs tokens for anybody in its user
> list, with whatever roles that list gives them, and its admin UI has no login.
> Anyone who can reach it can mint a token for any user it holds. Run it on a
> development machine and nowhere else.

## Purpose

A simplified IdP that persists users and clients as JSON on disk, signs tokens
with its own keyring, and checks client credentials on every code exchange.

Supports OAuth2 Authorization Code, OpenID Connect (id_token, userinfo, nonce),
Client Credentials, and Token Exchange (RFC 8693).

## Quick start

```bash
uv sync
uv run uvicorn app.main:app --port 9001 --reload
```

Or with Docker:

```bash
docker compose up
```

Then open <http://localhost:9001/> to add, edit and delete users and clients.

On first run it seeds `instance/users.json` with nine personas and one client.
Seeding is skipped when the file exists, so it never overwrites your edits.
Delete the file to start over.

## Integration

Point your app's OIDC/OAuth2 config at local-idp:

```bash
OIDC_ISSUER="http://localhost:9001"
OIDC_AUDIENCE="dev"
OIDC_CLIENT_ID="dev-client"
OIDC_CLIENT_SECRET="dev-secret"
```

The issuer must be the address the service actually reaches, because a client
fetches `/.well-known/openid-configuration` from it and compares the `issuer` it
gets back.

## Endpoints

| Path                                | What it does                                           |
| ----------------------------------- | ------------------------------------------------------ |
| `/`                                 | Admin UI: list, add, edit and delete users and clients |
| `/.well-known/openid-configuration` | OIDC discovery document                                |
| `/.well-known/jwks.json`            | Public signing keys                                    |
| `/dev/authorize`                    | Sign-in page listing stored users                      |
| `/dev/token`                        | Code exchange, client credentials, token exchange      |
| `/dev/userinfo`                     | Returns claims for a bearer token                      |
| `/api/users`                        | User list as JSON (CRUD)                               |
| `/api/clients`                      | Client registry as JSON (CRUD)                         |
| `/api/keys`                         | Signing keys and active key (CRUD + rotate)            |
| `/health`                           | Liveness check with user/client/key counts             |

## Documentation

Full documentation with flow diagrams, configuration reference, and API
details:

```bash
uv sync --group docs
uv run mkdocs serve
```

Then open <http://localhost:8000/>.

## Signing keys

Keys live in `instance/keys.json` and survive restarts. Several keys can be
published at once for rotation testing:

```bash
# Rotate: sign with a new key, keep publishing the old one
curl -sX POST localhost:9001/api/keys -H 'Content-Type: application/json' \
  -d '{"make_active":true}'

# Publish a key without signing with it yet
curl -sX POST localhost:9001/api/keys -H 'Content-Type: application/json' \
  -d '{"make_active":false}'

# Cut over to it
curl -sX POST localhost:9001/api/keys/<kid>/activate

# Retire one, so tokens it signed stop verifying
curl -sX DELETE localhost:9001/api/keys/<kid>
```

`instance/keys.json` holds private halves. It is gitignored.

## Token minting

```bash
curl -sX POST localhost:9001/dev/token \
  -H 'Content-Type: application/json' \
  -d '{"subject":"019b76da-b3b8-741c-ada2-4c1da1ed4927"}'
```

A subject that matches a stored user fills in their roles and permissions
automatically. Pass `roles` or `permissions` explicitly to mint something
nobody is stored with.

## Testing

A registered client's secret is compared on every code exchange, so a service
configured with the wrong one gets a `401` here rather than in staging.

`enforce_secret` on a client controls whether the secret is checked. Turn it
off mid-migration to let a caller through while somebody fixes the
configuration. `redirect_uris` restricts where codes can be sent; an empty list
accepts any redirect.

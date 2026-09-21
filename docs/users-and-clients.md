# Users & Clients

local-idp stores users and OAuth2 clients as JSON files on disk. You can manage
them through the admin UI at [localhost:9001](http://localhost:9001) or through
the JSON API.

## Users

A user represents a person who can sign in. Each user maps to a set of token
claims.

| Field | Required | Purpose |
| ----- | -------- | ------- |
| `key` | yes | URL-safe handle, used in the admin UI and API (e.g. `maya`) |
| `subject` | yes | The `sub` claim in tokens. Typically a UUID. This is the stable identifier your app uses |
| `name` | no | The `name` claim |
| `email` | no | The `email` claim |
| `purpose` | no | Description shown in the admin UI |
| `roles` | no | Array of strings in the `roles` claim |
| `permissions` | no | Array of strings in the `permissions` claim |

### Seed users

On first run, 9 users are created with different role combinations:

| Key | Name | Notes |
| --- | ---- | ----- |
| `maya` | Maya Okonkwo | Personal space only |
| `tom` | Tom Reilly | Personal space only |
| `sana` | Sana Qureshi | Personal space only |
| `alice` | Alice Admin | Owner of Acme org |
| `bob` | Bob Editor | Member of Acme org |
| `priya` | Priya Nair | Admin of Acme org |
| `eve` | Eve Guest | In Acme org, no workspace access |
| `nomad` | Noa Nomad | No space, no org |
| `stale` | Stale Session | Member of Acme org |

### Admin UI

- Browse all users at [localhost:9001](http://localhost:9001)
- Click a user to edit their fields
- Add new users with the form at the bottom of the page
- Delete users from their edit page

### API

| Method | Path | Body | Response |
| ------ | ---- | ---- | -------- |
| `GET` | `/api/users` | -- | `[{User}]` |
| `GET` | `/api/users/{key}` | -- | `{User}` or 404 |
| `POST` | `/api/users` | `{ key, subject, name?, email?, purpose?, roles?, permissions? }` | `{User}` (201) or 409 if key exists |
| `PATCH` | `/api/users/{key}` | Any user fields to update | `{User}` (200) or 404 |
| `DELETE` | `/api/users/{key}` | -- | 204 or 404 |

Example:

```bash
# Create a user
curl -X POST http://localhost:9001/api/users \
  -H 'Content-Type: application/json' \
  -d '{"key": "test", "subject": "user-test", "name": "Test User", "roles": ["viewer"]}'

# Update their roles
curl -X PATCH http://localhost:9001/api/users/test \
  -H 'Content-Type: application/json' \
  -d '{"roles": ["admin"]}'

# Delete them
curl -X DELETE http://localhost:9001/api/users/test
```

## Clients

A client is an OAuth2 application registration. It controls which `client_id`
and `client_secret` pairs are accepted at the token endpoint.

| Field | Required | Purpose |
| ----- | -------- | ------- |
| `client_id` | yes | OAuth2 client identifier |
| `client_secret` | no | Checked on token exchange. Compared with constant-time comparison |
| `name` | no | Display name |
| `redirect_uris` | no | Allowed redirect URIs. Empty means any URI is accepted |
| `enforce_secret` | no | Default `true`. When `false`, any secret is accepted |

### Seed client

One client is created on first run:

| Field | Value |
| ----- | ----- |
| `client_id` | `dev-client` |
| `client_secret` | `dev-secret` |
| `name` | Local development |
| `enforce_secret` | `true` |

### API

| Method | Path | Body | Response |
| ------ | ---- | ---- | -------- |
| `GET` | `/api/clients` | -- | `[{Client}]` (secrets included) |
| `POST` | `/api/clients` | `{ client_id, client_secret?, name?, redirect_uris?, enforce_secret? }` | `{Client}` (201) or 409 |
| `DELETE` | `/api/clients/{client_id}` | -- | 204 or 404 |

Example:

```bash
# Register a new client
curl -X POST http://localhost:9001/api/clients \
  -H 'Content-Type: application/json' \
  -d '{"client_id": "my-app", "client_secret": "my-secret", "name": "My App"}'
```

## Signing keys

local-idp manages its own signing keys. On first run, it generates an ES256
key. You can add more keys and rotate between them.

| Method | Path | Body | Response |
| ------ | ---- | ---- | -------- |
| `GET` | `/api/keys` | -- | `{ active: kid, keys: [{JWK}] }` |
| `POST` | `/api/keys` | `{ algorithm: "ES256"\|"ES384"\|"ES512"\|"RS256", make_active?: bool }` | `{ kid, active }` (201) |
| `POST` | `/api/keys/{kid}/activate` | -- | `{ active: kid }` (200) or 404 |
| `DELETE` | `/api/keys/{kid}` | -- | 204, 404, or 409 (can't delete active key) |

The active key signs all new tokens. Inactive keys remain in the JWKS so
tokens signed before a rotation can still be verified.

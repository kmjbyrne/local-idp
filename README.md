# Local IdP

An identity provider for local development, with an editable user list.

> [!WARNING] This is a test fixture. It signs tokens for anybody in its user
> list, with whatever roles that list gives them, and its admin UI has no login.
> Anyone who can reach it can mint a token for any user it holds. Run it on a
> development machine and nowhere else.

**But we have IdP at home!**

## Purpose

Works in concert with `oidcutils`
(<https://github.com/kmjbyrne/python-oidcutils>).

Identities are a tuple compiled into the application in the library, so adding a
test user means editing Python and restarting, and its token endpoint never
checks client credentials.

This service stands up a simplified IdP service that persists users, includes a
web form for CRUD of those users, and registered clients have secrets that are
actually compared.

Signing, key publication and the code exchange are still `oidcutils.dev`. This
service decides who may ask but it does not decide how a token is made ⚠️.

## Getting Started

```bash
uv sync
uv run uvicorn main:app --port 9000
```

Or with Docker, which bind-mounts `instance/` so the JSON survives a restart and
can be read from the host:

```bash
docker compose up
```

Then open <http://localhost:9000/> to add, edit and delete users and clients.

On a first run it writes `instance/users.json` with nine personas whose subject
ids would match those of our resource provider db seeds, plus one client.
Seeding is skipped whenever the file already exists, so it never overwrites your
edits. To start over, delete the file.

## Integration

Set the issuer to wherever this service answers, and the audience to whatever
you want in the `aud` claim:

```bash
OIDC_ISSUER="http://localhost:9000"
OIDC_AUDIENCE="eagata"
OIDC_CLIENT_ID="dev-client"
OIDC_CLIENT_SECRET="dev-secret"
```

The issuer must be the address the service actually reaches, because a client
fetches `/.well-known/openid-configuration` from it and compares the `issuer` it
gets back. Behind a proxy that means the external URL, not the container name.

## Endpoints

| Path                                | What it does                                           |
| ----------------------------------- | ------------------------------------------------------ |
| `/`                                 | Admin UI: list, add, edit and delete users and clients |
| `/.well-known/openid-configuration` | Discovery                                              |
| `/.well-known/jwks.json`            | The public key that verifies these tokens              |
| `/dev/authorize`                    | Sign-in page listing the stored users                  |
| `/dev/token`                        | Exchanges a code, or mints from a JSON body            |
| `/api/users`                        | The user list as JSON                                  |
| `/api/clients`                      | The client registry as JSON                            |
| `/api/keys`                         | The signing keys, and which one is active              |
| `/health`                           | Liveness, plus how many users and clients are stored   |

## Testing

A registered client's secret is compared on every code exchange, so a service
configured with the wrong one gets a `401` here rather than in staging.

Register a client with `enforce_secret` on, which is the default, and post a
different secret to watch it refuse. Turn `enforce_secret` off for a client
mid-migration, and the wrong secret goes through, so a caller that was never
sending the right one keeps working while somebody fixes it. Give a client a
`redirect_uris` list and anything outside it is refused; leave the list empty
and any redirect is accepted.

An empty registry accepts any credentials, so a first run is not blocked by
configuration that does not exist yet.

## Signing Keys

Keys live in `instance/keys.json` and survive a restart, so a client holding a
cached JWKS is not broken by one. `oidcutils` generates an ephemeral key at
import instead, which is right for a library and wrong for a service something
else fetches keys from.

Several keys can be published at once, which is what makes a rotation testable:

```bash
# Rotate: sign with a new key, keep publishing the old one
curl -sX POST localhost:9000/api/keys -H 'Content-Type: application/json' \
  -d '{"make_active":true}'

# Publish a key without signing with it yet, to warm a client's cache
curl -sX POST localhost:9000/api/keys -H 'Content-Type: application/json' \
  -d '{"make_active":false}'

# Cut over to it
curl -sX POST localhost:9000/api/keys/<kid>/activate

# Retire one, so tokens it signed stop verifying
curl -sX DELETE localhost:9000/api/keys/<kid>
```

A token names its key in the `kid` header, so a client knows which of the
published keys to check it against. Rotating keeps old tokens working until they
expire; retiring does not, which is the case client error handling rarely gets
tested against. `RS256` is accepted as well as the EC algorithms, so a client
can be checked against both.

`instance/keys.json` holds private halves. It is gitignored, and it is the one
file here worth keeping out of a repository.

## Token Minting

```bash
curl -sX POST localhost:9000/dev/token \
  -H 'Content-Type: application/json' \
  -d '{"subject":"019b76da-b3b8-741c-ada2-4c1da1ed4927"}'
```

A subject that matches a stored user is filled in from that user, so a test gets
their roles without repeating them. Pass `roles` or `permissions` explicitly to
mint something nobody is stored with.

## Layout

Two JSON files live in `instance/`, and both can be edited by hand. Writes are
atomic, so a crash partway through leaves the previous file rather than a
truncated one.

- `users.json` holds `key`, `subject`, `name`, `email`, `roles`, `permissions`
  and `purpose`. `subject` is the one that matters: it becomes the token's `sub`
  claim, which is all a consuming service knows a person by.
- `clients.json` holds `client_id`, `client_secret`, `name`, `redirect_uris` and
  `enforce_secret`.
- `keys.json` holds the signing keys, private halves included, and which one is
  active.

## Sharing Personas With A Service

`GET /api/users` returns the list, so a service can read the personas rather
than keeping its own copy of them:

```bash
curl -s localhost:9000/api/users
```

What crosses over is identity: `subject`, `name`, `email`, `roles`,
`permissions`. What does not is anything the consuming service owns. An identity
server does not know what an organization is, so memberships, spaces and
per-workspace reach stay in the service that has those concepts, keyed on `key`
or `subject`.

That split is what keeps this reusable. A service reads subjects from here
instead of hardcoding them, which removes the drift where two lists disagree
about who somebody is, and keeps its own domain shape to itself.

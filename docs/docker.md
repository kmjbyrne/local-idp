# Docker

local-idp ships with a Dockerfile and docker-compose configuration for running
it anywhere without installing Python or uv.

## Quick start

```bash
docker compose up
```

This builds the image and starts local-idp on
[localhost:9001](http://localhost:9001). The dev override mounts the source for
live reload and binds `./instance` so you can edit users and clients as files.

## Production-style run

To run without the dev override (no reload, no source mount, named volume for
instance data):

```bash
docker compose -f docker-compose.yml up -d
```

## Build only

```bash
docker build -t mock-idp:local .
docker run -p 9001:9001 mock-idp:local
```

## Environment variables

Pass configuration through environment variables or a `.env` file:

```bash
docker compose up -e ISSUER=https://idp.example.com -e AUDIENCE=my-app
```

Or in `docker-compose.yml`:

```yaml
environment:
  ENVIRONMENT: ${ENVIRONMENT:-development}
  ISSUER: ${ISSUER:-http://localhost:9001}
  AUDIENCE: ${AUDIENCE:-dev}
```

See [Configuration](configuration.md) for all available variables.

## Data persistence

| Mode | Instance data stored in | Survives `docker compose down`? |
| ---- | ----------------------- | ------------------------------- |
| Development (default) | `./instance/` bind mount | Yes (local files) |
| Production (`-f docker-compose.yml`) | `instance` named volume | Yes (until `docker volume rm`) |

The instance directory holds `users.json`, `clients.json`, and `keys.json`.
On first run, seed data is written if these files don't exist.

To reset to defaults, delete the instance directory or volume:

```bash
# Development
rm -rf instance/

# Production
docker volume rm mock-idp_instance
```

## Health check

The compose configuration includes a health check against `/health`:

```bash
curl http://localhost:9001/health
```

Returns the count of users, clients, and keys, and verifies the instance
files are readable.

## Including in another compose stack

Reference local-idp from your app's compose file:

```yaml
services:
  app:
    build: .
    depends_on:
      mock-idp:
        condition: service_healthy
    environment:
      OIDC_ISSUER: http://mock-idp:9001

  mock-idp:
    image: mock-idp:local
    build:
      context: ../local-idp
    ports:
      - "9001:9001"
    environment:
      ISSUER: http://mock-idp:9001
```

Set `ISSUER` to the Docker network hostname (`mock-idp:9001`), not
`localhost`, so token validation works between containers.

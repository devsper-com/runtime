---
title: Self-hosting the Registry
---

# Self-hosting the Registry

You can run your own instance of the hivemind plugin registry. The entire stack -- API, web UI, PostgreSQL, and Caddy reverse proxy -- is defined in a single Docker Compose file.

## Prerequisites

- Docker and Docker Compose v2+
- A domain name with DNS pointing to your server (for TLS)
- At least 1 GB RAM and 10 GB disk

Optional: S3-compatible object store for package files, GitHub/Google OAuth credentials, SMTP or AWS SES for emails.

## Quick Start

### 1. Clone and Configure

```bash
git clone https://github.com/rithul/hivemind.git
cd hivemind/registry
cp .env.prod.example .env.prod
```

Edit `.env.prod` and set the required variables:

| Variable | Description |
|---|---|
| `POSTGRES_PASSWORD` | Database password -- generate with `openssl rand -base64 32` |
| `JWT_SECRET` | JWT signing secret (min 32 bytes) |
| `INTERNAL_SECRET` | Shared secret between services (min 32 chars in production) |
| `BASE_URL` | Public URL (e.g., `https://registry.example.com`) |
| `DOMAIN` | Domain for Caddy TLS certificates |

Optional variables include `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET` (OAuth), `S3_BUCKET`/`S3_REGION` (storage), `SES_REGION`/`SES_FROM_ADDRESS` or `SMTP_HOST`/`SMTP_PORT` (email), `RATE_LIMIT_RPS` (default 10), and `MAX_UPLOAD_SIZE_MB` (default 100).

### 2. Configure Caddy

Edit `registry/deploy/Caddyfile` and replace the domain:

```caddyfile
registry.example.com {
    handle /internal/* {
        respond "Not Found" 404
    }
    handle /api/* {
        reverse_proxy api:8080
    }
    handle /simple/* {
        reverse_proxy api:8080
    }
    handle {
        reverse_proxy web:3000
    }
}
```

Caddy provisions TLS certificates automatically via Let's Encrypt. Ensure ports 80 and 443 are open.

### 3. Start the Services

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

This starts four containers on an internal Docker network (`registry-net`):

| Service | Port | Description |
|---|---|---|
| `postgres` | 5432 (internal) | PostgreSQL 15 |
| `api` | 8080 (internal) | Go API server |
| `web` | 3000 (internal) | React web frontend |
| `caddy` | 80, 443 (public) | TLS and reverse proxy |

## Database Migrations

Migrations run automatically on API startup. To run them in isolation:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  run --rm -e MIGRATE_ONLY=1 api
```

## Monitoring

The API exposes two health endpoints:

- `GET /health` -- liveness (returns 200 if the process is running)
- `GET /ready` -- readiness (returns 200 if the database is reachable)

View logs with `docker compose -f docker-compose.prod.yml logs -f` or target a specific service (e.g., `logs -f api`). Caddy writes JSON access logs to `/var/log/caddy/access.log`.

## Backups

Back up PostgreSQL with `pg_dump`:

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U registry hivemind_registry > backup_$(date +%Y%m%d).sql
```

Database data is persisted in the `postgres-data` Docker volume. Set up automated daily backups to S3 or another durable store for production. If using S3 for package files, those are already stored durably.

## Updating

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

Migrations run automatically on restart.

## Security Considerations

- The Caddyfile blocks external access to `/internal/*` endpoints.
- `INTERNAL_SECRET` must be at least 32 characters when `ENV=production`.
- `JWKS_URL` must use HTTPS in production to prevent MITM on JWT verification.
- Caddy sets HSTS, `X-Content-Type-Options`, `X-Frame-Options`, and CSP headers.
- Rate limiting is enforced per IP. Set `TRUSTED_PROXY` if Caddy runs on a separate host.
- Uploads are validated for extension (`.whl`/`.tar.gz` only), ZIP integrity, and size.

## Custom Domain

1. Set `DOMAIN` and `BASE_URL` in `.env.prod`
2. Update the Caddyfile domain
3. Point your DNS A record to the server
4. Restart Caddy -- it obtains a certificate automatically

## Pointing the CLI at Your Instance

```bash
export HIVEMIND_REGISTRY_URL=https://registry.example.com
hivemind reg login
```

Or install packages directly with pip:

```bash
pip install --index-url https://registry.example.com/simple/ hivemind-plugin-example
```

## Next Steps

- [Registry Overview](/docs/registry/overview) -- architecture and features
- [API Reference](/docs/registry/api-reference) -- full endpoint documentation
- [Publishing to the Registry](/docs/registry/publishing) -- how to publish plugins

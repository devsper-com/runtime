---
title: API Reference
---

# Registry API Reference

The hivemind registry exposes a RESTful JSON API for managing packages, versions, and accounts. The CLI uses this API internally; you can also call it directly for automation and CI integration.

## Base URL

```
https://registry.hivemind.rithul.dev/api/v1
```

## Authentication

Authenticated endpoints require one of:

- **API key** -- pass in the `X-API-Key` header. Create keys from the web dashboard or via `/api/v1/me/api-keys`.
- **Bearer token** -- pass a JWT in the `Authorization: Bearer <token>` header.

API keys carry scopes (`read`, `publish`) that determine access. Endpoints below are marked **public**, **read**, or **publish**.

## Rate Limiting

| Endpoint Group | Limit |
|---|---|
| General authenticated | 10 req/s per IP |
| Search | 60 req/s per IP |
| Upload | 10 req/s per IP |
| Device auth | 5 req/s per IP |

Rate limits are configurable via `RATE_LIMIT_RPS`. Exceeding the limit returns `429 Too Many Requests`.

## Package Endpoints

### List Packages -- `GET /api/v1/packages` (public)

Query parameters: `namespace` (filter by org), `page` (default 1, 20 per page).

```json
{ "packages": [{ "id": "uuid", "name": "hivemind-plugin-example", "description": "...", "total_downloads": 42 }], "page": 1 }
```

### Get Package -- `GET /api/v1/packages/:name` (public)

Returns full metadata for a single package. Names are normalized per PEP 503.

### Create Package -- `POST /api/v1/packages` (publish)

Registers a new package. The CLI calls this automatically during publish if the package does not exist.

```json
{ "Name": "hivemind-plugin-example", "DisplayName": "Example Plugin", "Description": "...", "Homepage": "https://...", "Repository": "https://...", "License": "MIT", "Keywords": ["example"] }
```

Returns `201 Created` or `409 Conflict` if the name is taken.

### Update Package -- `PUT /api/v1/packages/:name` (publish, owner only)

Updates metadata (description, homepage, keywords, etc.).

### Delete Package -- `DELETE /api/v1/packages/:name` (publish, owner only)

Permanently deletes a package and all versions. Returns `204 No Content`.

## Version Endpoints

### List Versions -- `GET /api/v1/packages/:name/versions` (public)

```json
{ "versions": [{ "version": "0.1.0", "published": true, "yanked": false, "verification_status": "passed", "tool_count": 3 }] }
```

### Get Version -- `GET /api/v1/packages/:name/:version` (public)

Returns metadata for a specific version.

### Get Version Status -- `GET /api/v1/packages/:name/versions/:version/status` (public)

Returns verification status and report:

```json
{ "version": "0.1.0", "verification_status": "passed", "published": true, "tool_count": 3, "verification_report": null }
```

### Upload -- `POST /api/v1/packages/:name/upload` (publish)

Uploads a distribution file via `multipart/form-data`.

| Field | Type | Description |
|---|---|---|
| `file` | file | `.whl` or `.tar.gz` distribution file |
| `name` | string | Package name (fallback if not in URL) |
| `version` | string | Version string (required) |

A generic endpoint at `POST /api/v1/packages/upload` is also available for Twine compatibility. Max upload size: 100 MB (configurable via `MAX_UPLOAD_SIZE_MB`).

Returns `201 Created`, `400` (invalid input), `404` (package not found), or `409` (version exists).

### Yank -- `POST /api/v1/packages/:name/:version/yank` (publish, owner only)

Marks a version as yanked (hidden from Simple index, still downloadable by exact version).

```json
{ "reason": "critical security issue" }
```

Returns `200 OK`.

### Delete Version -- `DELETE /api/v1/packages/:name/:version` (publish, owner only)

Permanently removes a version. Returns `204 No Content`. Prefer yanking over deletion.

## Search

### Search Packages -- `GET /api/v1/search` (public)

Full-text search using PostgreSQL `tsvector`. Query parameters: `q` (required), `page` (default 1).

```json
{ "results": [{ "name": "hivemind-plugin-web", "description": "...", "total_downloads": 150, "verified": true }], "page": 1 }
```

## Other Endpoints

### Global Stats -- `GET /api/v1/stats` (public)

Returns aggregate registry statistics (total packages, downloads, etc.).

### Simple Repository API (PEP 503)

```
GET /simple/                    # Package index
GET /simple/:name/              # Package file listing
GET /simple/:name/:filename     # File download (redirects to S3)
```

These are public endpoints for `pip` and `uv` compatibility. No authentication required.

## Error Codes

| Code | Meaning |
|---|---|
| `400` | Bad request (invalid input) |
| `401` | Unauthorized (missing or invalid credentials) |
| `403` | Forbidden (not the package owner) |
| `404` | Not found |
| `409` | Conflict (duplicate name or version) |
| `429` | Rate limit exceeded |
| `500` | Internal server error |
| `503` | Service unavailable (storage not configured) |

## Next Steps

- [Publishing to the Registry](/docs/registry/publishing) -- CLI workflow for publishing
- [Registry Overview](/docs/registry/overview) -- architecture and features
- [Self-hosting the Registry](/docs/self-hosting/registry) -- deploy your own instance

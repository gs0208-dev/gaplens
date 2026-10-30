# API

Base path `/api/v1`. JSON unless stated. Authenticated endpoints require `Authorization: Bearer <access token>`. Health endpoints are at the root, outside `/api/v1`, because platforms probe them directly.

This file is the contract. Change it in the same commit as the code. Fields not listed here must not be returned.

## Conventions

- IDs are UUID strings. Timestamps are ISO 8601 in UTC.
- Request bodies reject unknown fields (422).
- Lists use keyset pagination: `?limit=20&cursor=<opaque>`; default limit 20, maximum 100. Response: `{ "items": [...], "next_cursor": "..." | null }`.
- Long-running work returns `202 Accepted` with a resource the client polls. Polling interval 2 seconds, with the status field as the source of truth.
- Rate-limited responses are `429` with a `Retry-After` header.

## Error format

Every error response uses this shape (modeled on RFC 9457 problem details):

```json
{
  "type": "about:blank",
  "title": "Document not found",
  "status": 404,
  "code": "document_not_found",
  "detail": "No document with this id.",
  "request_id": "8f3c2a9e-..."
}
```

`code` is a stable machine-readable value. `detail` is safe for display. Validation errors (422) add `errors: [{ "field": "email", "message": "..." }]`. Stack traces and internal messages never appear.

Error codes in use: `validation_error` (422), `email_already_registered` (409), `invalid_credentials` (401), `invalid_access_token` (401), `invalid_refresh_token` (401), `origin_not_allowed` (403), `rate_limited` (429), `internal_error` (500). Add a code to this list in the same commit as the code that returns it.

Status codes: 400 malformed input, 401 missing or invalid token, 403 request from an origin that is not allowed, 404 not found or not yours, 409 conflict (duplicate upload, analysis already running, email in use), 413 file too large, 415 unsupported file type, 422 validation, 429 rate limit, 500 unexpected, 503 dependency down.

## Operations (no auth)

| Method | Path | Result |
|---|---|---|
| GET | `/health/live` | `200 { "status": "ok" }` while the process runs |
| GET | `/health/ready` | `200 { "status": "ok", "database": "up" }` or `503 { "status": "unavailable", "database": "down" }` |

## Auth (Sprint 1)

| Method | Path | Body | Success |
|---|---|---|---|
| POST | `/auth/register` | `{ email, password }` | `201 { user }` |
| POST | `/auth/login` | `{ email, password }` | `200 { access_token, expires_in, user }` and sets the refresh cookie |
| POST | `/auth/refresh` | none (cookie) | `200 { access_token, expires_in, user }`, rotates the cookie |
| POST | `/auth/logout` | none (cookie) | `204`, revokes the token, clears the cookie |
| GET | `/auth/me` | none | `200 { user }` |

Register: the email is trimmed and lowercased, at most 254 characters. The password is 12 to 128 characters and is never trimmed or truncated. A duplicate email (compared ignoring case) is `409 email_already_registered`. Unknown fields are `422`.

Login: the email is trimmed and lowercased; the password is 1 to 128 characters. A wrong password, an unknown email and a disabled account all return the same `401 invalid_credentials`. No cookie is set on failure. `expires_in` is the access token lifetime in seconds (900). The refresh token is only ever in the cookie, never in the body.

Refresh: the request must carry an `Origin` header that exactly matches an entry in `CORS_ORIGINS`, otherwise `403 origin_not_allowed`, and the refresh token is not touched. The old refresh token is revoked and a new one in the same login (family) is set in the cookie. A missing, unknown, expired or already-used token all return the same `401 invalid_refresh_token` and clear the cookie. Presenting an already-used token also revokes every token of that login. A disabled account gets the same `401` and loses the login.

Me: needs `Authorization: Bearer <access token>`. A missing header, another scheme, and an expired, forged, unsigned or wrong-audience token all return the same `401 invalid_access_token` with `WWW-Authenticate: Bearer`, as does a valid token for a deleted or disabled user. The role is read from the database, not from the token.

Logout: needs the same allowed `Origin` as refresh (`403 origin_not_allowed` otherwise). It revokes every active token of the login that the cookie's token belongs to, even if the cookie holds an older, already-rotated token, and clears the cookie. It always returns `204`, including when the cookie is missing, unknown or already revoked, so logging out twice is harmless. An access token already issued keeps working until it expires, at most 15 minutes, so the client should drop it from memory on logout.

Rate limits: login is 5 requests per minute per IP, and an email address is blocked for up to 15 minutes after 5 failed logins, from any IP. Register is 5 per hour per IP. A limited request gets `429 rate_limited` with a `Retry-After` header in seconds. For the IP limits it is the window length, an upper bound on the wait.

`user`: `{ id, email, role, created_at }`. Cookie: `refresh_token; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`.

## Documents (Sprint 2)

| Method | Path | Notes |
|---|---|---|
| POST | `/documents` | `multipart/form-data` with `file` and optional `title`. `202 { document }` |
| GET | `/documents` | Paginated list of `{ id, title, status, page_count, chunk_count, created_at }` |
| GET | `/documents/{id}` | Full document metadata including `status` and `error_message` |
| GET | `/documents/{id}/chunks` | Ordered chunks `{ id, chunk_index, section_label, heading, content, page_start }` for the source pane (document must be `ready`) |
| DELETE | `/documents/{id}` | `204`; soft delete |

`document`: `{ id, title, filename, mime_type, size_bytes, status, error_message, page_count, chunk_count, created_at }`.

## Chat (Sprint 2 backend, Sprint 3 UI)

| Method | Path | Notes |
|---|---|---|
| POST | `/documents/{id}/chat` | Body `{ question, thread_id? }`. Creates a thread if none is given. `200 { thread_id, message }` |
| GET | `/documents/{id}/threads` | Paginated threads |
| GET | `/threads/{id}/messages` | Messages in order |

`message`: `{ id, role, content, grounded, citations: [{ chunk_id, section_label, quote }], created_at }`. `question` is 1 to 1000 characters.

## Analyses and findings (Sprint 3)

| Method | Path | Notes |
|---|---|---|
| POST | `/documents/{id}/analyses` | Starts a gap report. `202 { analysis }`. `409` if one is already running |
| GET | `/documents/{id}/analyses/latest` | Latest analysis with findings and citations, or `404` |
| GET | `/analyses/{id}` | Analysis with findings |
| PATCH | `/findings/{id}` | Body `{ review_status }` with `open`, `confirmed` or `dismissed` |

`analysis`: `{ id, document_id, status, summary, findings_count, error_message, created_at, completed_at, findings: [finding] }`.
`finding`: `{ id, kind, severity, title, description, suggested_question, review_status, citations: [{ chunk_id, section_label, quote }] }`.

## Account (Sprint 4)

| Method | Path | Notes |
|---|---|---|
| DELETE | `/auth/me` | Body `{ password }`. Deletes the user and all their data. `204` |

## Versioning

Breaking changes get a new prefix (`/api/v2`). Additive changes (new optional fields) stay in `v1`.

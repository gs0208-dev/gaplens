# Security

GapLens stores people's confidential business documents and sends them to an LLM provider. Security is a feature, not a final step. The rules here are checked in code review and by tests.

## Assets and trust boundaries

- Assets: uploaded document text, gap reports and chats derived from it, user credentials, the LLM API key, the JWT signing secret.
- Trusted: server code, the database, environment configuration.
- Untrusted: the browser, every HTTP request, every uploaded file, document text, and everything the LLM returns.

## Threat model

| Threat | Control | Sprint |
|---|---|---|
| Broken object-level authorization (user A reads user B's document, report or chat) | Every repository method takes `owner_id` and filters on it; 404 for non-owned resources; an automated test per resource type | 1 onward |
| Credential stuffing, brute force | Rate limit login per IP and per email; generic error message; argon2id; dummy hash verification when the email is unknown so timing does not reveal accounts | 1 |
| Stolen access token (XSS) | Access token lives in memory only, 15-minute lifetime; strict CSP; no `dangerouslySetInnerHTML`; React escaping for all model output | 1, 3 |
| Stolen refresh token | Opaque random 256-bit value, stored hashed, httpOnly + Secure + SameSite=Strict cookie scoped to the auth path, rotated on every use; reuse of a rotated token revokes the whole token family | 1 |
| CSRF on cookie-authenticated endpoints (`/auth/refresh`, `/auth/logout`) | SameSite=Strict plus an `Origin` header check against the allowed origin list; other endpoints use a bearer header, which browsers do not attach cross-site | 1 |
| Malicious or oversized upload | Size cap, content-type by magic bytes, page cap, text-length cap, encrypted PDFs rejected, filename never used as a path, original file not stored | 2 |
| Prompt injection through document text | Document is wrapped as delimited data; model has no tools and no write access; output validated by schema; every citation verified against stored text; output never rendered as HTML | 3 |
| Cost abuse (large or repeated LLM calls) | Document size cap; `max_tokens` on every call; one active analysis per document; per-user rate limits; per-user daily token budget from `llm_calls` | 3, 4 |
| Sensitive data in logs | Structured logging with an allowlist of fields; tests assert that passwords, tokens and document text never reach logs | 1 onward |
| Secret leakage via git | `.env` ignored, `.env.example` placeholders only, secret scanning in CI and a pre-commit hook | 0, 4 |
| Vulnerable dependencies | Lockfiles, `pip-audit` and `npm audit` in CI, Dependabot weekly | 0, 4 |
| SQL injection | SQLAlchemy with bound parameters only; raw SQL via `text()` with bind parameters; never string formatting | all |
| Denial of service through slow parsing | Parsing runs off the event loop with size and page limits; request body limit at the proxy and in the app | 2, 4 |
| Data left behind after deletion | Cascading deletes; soft-deleted documents purged after 30 days; account deletion removes all user data | 2, 4 |

## Authentication

- Register: email (lowercased for uniqueness) and password. Password length 12 to 128, no composition rules, never truncated.
- Hashing: argon2id through `argon2-cffi`. Start from the library defaults and check on the deploy instance that one hash takes roughly 50 to 100 ms. Rehash on login if parameters change.
- Access token: JWT signed with HS256, secret of at least 32 random bytes from the environment. Claims: `sub` (user id), `role`, `iat`, `exp` (15 minutes), `iss`, `aud`. Verification always passes the expected algorithm list explicitly and requires `exp`, `iss` and `aud`. Tokens with `alg: none` or another algorithm are rejected.
- Refresh token: `secrets.token_urlsafe(32)`, stored as SHA-256 hex in `refresh_tokens`, lifetime 7 days, sent only in the cookie `refresh_token` with attributes `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`. Each refresh issues a new token and revokes the old one (`replaced_by`). Presenting a revoked token revokes the entire `family_id` and writes an `auth.refresh_reuse_detected` audit event.
- Page reload: the client calls `/auth/refresh` to obtain a new access token. There is no token in `localStorage` or `sessionStorage`.
- Same-origin deployment: the frontend host proxies `/api/*` to the backend so the refresh cookie is first-party (ADR-008). Without this, third-party cookie blocking breaks the flow.
- Logout revokes the current refresh token and clears the cookie.

## Authorization

- Roles: `user` and `admin`. In v1 only `user` is used by features; `admin` exists for operations and has no extra UI.
- Ownership is the main rule. Services receive `current_user` and pass `owner_id` down. Handlers never read `owner_id` from request bodies or query strings.
- A missing resource and a resource owned by someone else produce the same 404 response body.

## Input validation

- All request bodies are Pydantic models with explicit limits (`max_length`, enums). Unknown fields are rejected (`extra="forbid"`).
- Uploads:
  - Maximum 5 MB, at most 100 pages, extracted text at most 300,000 characters (limits are config values).
  - Allowed: PDF (starts with `%PDF-`), plain text and Markdown (valid UTF-8, no NUL bytes). Everything else is rejected with 415.
  - PDFs that are encrypted or produce no extractable text are rejected with a clear message (no OCR).
  - Duplicates (same `sha256` for the same owner) are rejected with 409.
  - Parsing happens in a worker thread; Sprint 4 evaluates moving it to a subprocess with a timeout.
- Display strings (titles, filenames) are length-limited and treated as plain text everywhere.

## LLM-specific controls

These map to the OWASP Top 10 for LLM applications: prompt injection, sensitive information disclosure, improper output handling, excessive agency and unbounded consumption.

- Prompt injection is assumed possible. Defense in depth, because no single control is sufficient:
  1. Prompts state that text inside `<document>` is data and that instructions found there must be ignored and may be reported as a finding.
  2. The document is escaped (`<` and `>`) so it cannot close the delimiter.
  3. The model has no tools and no way to act; it only returns JSON.
  4. Output must match the schema; anything else is rejected.
  5. Citations are checked against stored text; findings with no verifiable evidence are dropped.
  6. The UI renders output as text, never as HTML.
  7. `evals/datasets/injection_sample.md` runs in every eval pass.
- Sensitive information: a prompt is built from exactly one document of exactly one owner. No cross-user cache, memory or shared context. The UI tells users that document text is sent to the LLM provider. No document text is stored in logs or `llm_calls`.
- Excessive agency: none by design. Do not add tool use or actions without a new ADR and a security review.
- Unbounded consumption: `max_tokens` on every call, request timeouts, document caps, per-user limits and daily token budget (see `docs/database.md`).

## Rate limits (starting values, tune with data)

| Endpoint group | Limit |
|---|---|
| `POST /auth/login` | 5 per minute per IP, 5 per 15 minutes per email |
| `POST /auth/register` | 5 per hour per IP |
| `POST /documents` | 10 per hour per user |
| `POST /documents/{id}/analyses` | 5 per hour per user |
| `POST /documents/{id}/chat` | 30 per hour per user |
| Everything else | 120 per minute per user |

Limits are in-memory (slowapi) while there is one backend instance. With more than one instance, move counters to Postgres or Redis. Behind a proxy, trust forwarded headers only from the platform's proxy addresses so IP limits cannot be spoofed.

## Transport and headers

- HTTPS only in production. HSTS on responses.
- Backend responses: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on auth and document endpoints.
- Frontend (host headers): `Content-Security-Policy` with `default-src 'self'`, `script-src 'self'`, `connect-src 'self'`, `img-src 'self' data:`, `font-src 'self'`, `style-src 'self' 'unsafe-inline'` (component libraries set inline positioning styles), `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`. Fonts are self-hosted, so there are no third-party requests.
- CORS: explicit origin list from config, credentials allowed only for those origins, never `*`.

## Secrets and configuration

- Secrets only in environment variables. Local `.env` is gitignored. Production values are set in the host dashboards.
- Generate the JWT secret with `openssl rand -hex 32`. Rotate by deploying a new secret; this logs everyone out, which is acceptable.
- Add a secret scanner (gitleaks) as a pre-commit hook and CI step in Sprint 1, using its current release.
- The LLM API key is used only inside `app/ai/client.py`.

## Logging and audit

- Application logs: request id, method, path (without query strings), status, duration, user id (UUID), event names. Never passwords, tokens, cookies, document text, prompts, model output, or full email addresses.
- `audit_events` records: `auth.register`, `auth.login`, `auth.login_failed`, `auth.logout`, `auth.refresh_reuse_detected`, `document.upload`, `document.delete`, `analysis.start`, `account.delete`. Append-only; the application database role has no `UPDATE` or `DELETE` on it.

## Containers and infrastructure

- Images use a pinned minor Python tag, run as a non-root user, contain no secrets, and have a healthcheck.
- The database port is bound to `127.0.0.1` locally and is not exposed publicly in production.
- Production database access uses the application role described in `docs/database.md`.
- Backups: use the managed database's automated backups; test one restore before launch.

## Security tests that must exist

1. Ownership: for each resource type (document, chunks, analysis, finding, thread, message), user B receives 404 for user A's id.
2. Token tests: expired token rejected; wrong signature rejected; `alg: none` rejected; wrong `aud` rejected.
3. Refresh rotation: old token fails after use; reuse revokes the family.
4. Login: wrong password and unknown email return the same response.
5. Rate limits: the 6th login attempt in a minute returns 429.
6. Upload: wrong magic bytes, oversize file, encrypted PDF and duplicate are all rejected.
7. Logs: a test captures logs during login and upload and asserts that no password, token or document text appears.
8. Injection eval passes (see `docs/ai-engineering.md`).

## Per-sprint security checklist

- Sprint 1: auth tests above, ownership helper, audit events, rate limit on login, gitleaks.
- Sprint 2: upload validation tests, ownership tests for documents and chunks, parsing limits.
- Sprint 3: prompt escaping, citation verification, schema validation, token budget, injection dataset.
- Sprint 4: CSP and headers, dependency audit made blocking, CORS review, container review, restore test, account deletion, final review against this file.

## Accepted risks (v1)

- Registration reveals whether an email is already registered (409). Revisit if the app becomes public.
- In-memory rate limiting resets on restart and is per instance.
- Text extraction libraries can have parser bugs; mitigated by caps and isolation, not eliminated.
- Document text goes to a third-party LLM provider. Acceptable for a portfolio project with fictional or non-confidential documents; do not market it for confidential data without a data processing review.

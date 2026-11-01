# Decisions

Architecture decision records. Append new entries at the bottom; never rewrite history. If a decision changes, add a new entry that supersedes the old one. Format: context, decision, consequences, alternatives.

## ADR-001: Monorepo with one backend and one frontend

Context: a single developer, one deployable product.
Decision: one repository containing `backend/`, `frontend/`, `docs/`, `evals/`, `infra/`.
Consequences: one place for agent rules and docs, simple CI, shared history. Backend and frontend still deploy separately.
Alternatives: two repositories (more overhead, no benefit at this size).

## ADR-002: FastAPI with async SQLAlchemy 2.x and Alembic

Context: the owner knows Python; the work is I/O-bound (database and LLM calls).
Decision: FastAPI, Pydantic v2, SQLAlchemy 2.x async with asyncpg, Alembic migrations.
Consequences: typed request and response models and generated OpenAPI. CPU-bound work (PDF parsing, embedding) must move off the event loop.
Alternatives: Django (heavier than needed), synchronous SQLAlchemy (simpler, but wastes workers while waiting on the LLM).

## ADR-003: One Postgres database with pgvector for everything

Context: users, documents, chunks and vectors are tightly related and small in volume.
Decision: store vectors in the same Postgres database as relational data.
Consequences: one system to run and back up, ownership filters and vector search in one query, transactional ingestion. Lower raw vector performance than a dedicated engine, which is irrelevant at this scale.
Alternatives: a separate vector database (more moving parts, no benefit here).

## ADR-004: Local embeddings with fastembed (ONNX), bge-small-en-v1.5

Context: embeddings must be free to run, private, and light enough for a low-cost host. A PyTorch-based stack is heavy for small instances.
Decision: `fastembed` with `BAAI/bge-small-en-v1.5`, 384 dimensions.
Consequences: no embedding API cost and no document text sent to a second provider. The model is bundled or downloaded at build time. Changing the model requires re-embedding.
Alternatives: sentence-transformers (needs PyTorch), a hosted embedding API (cost, privacy, another dependency). Revisit with eval numbers (recall@k) if retrieval is weak.

## ADR-005: shadcn/ui with Tailwind instead of Material UI

Context: the product should look purpose-built, and AI coding agents will edit the UI often.
Decision: shadcn/ui (component source copied into the repo) on Tailwind, icons from lucide-react.
Consequences: full control of tokens and markup, no runtime theme layer, easy for agents to modify. The owner maintains the component code. Material UI would give a recognizable look faster but is harder to make distinctive.
Alternatives: Material UI, Chakra, Mantine.

## ADR-006: Original uploads are not stored

Context: hosting disks are often ephemeral, and storing confidential files adds risk.
Decision: extract text and sections, store chunks, discard the original file. Keep only its SHA-256 for duplicate detection.
Consequences: smaller attack surface and no storage service. Users cannot download the original from GapLens, and re-processing needs a new upload.
Alternatives: object storage (cost and complexity not justified in v1).

## ADR-007: Gap report uses full-document context; chat uses RAG

Context: gap detection needs absence and cross-section contradictions; chat needs local, citable answers.
Decision: the gap report sends the whole document in one call; chat retrieves top-k chunks.
Consequences: report quality depends on document size limits (capped). The interview answer to "why RAG here?" is accurate: it is used where it fits.
Alternatives: RAG for both (misses absence), map-reduce for large documents (documented upgrade path).

## ADR-008: Same-origin API through a frontend proxy

Context: the frontend (Vercel) and backend (Render) are on different domains, and browsers block third-party cookies, which would break the httpOnly refresh cookie.
Decision: the frontend host rewrites `/api/*` to the backend; the Vite dev server proxies the same path.
Consequences: cookies are first-party, CORS is nearly irrelevant, `SameSite=Strict` works. Adds one hop and ties the frontend host to the backend URL configuration.
Alternatives: refresh token in `localStorage` (vulnerable to XSS theft), cross-site cookies with `SameSite=None` (unreliable under third-party cookie blocking), one custom domain for both (best option if a domain is acquired).

## ADR-009: Exact vector search, no HNSW index in v1

Context: retrieval is always scoped to one document with a few hundred chunks.
Decision: no vector index; `ORDER BY embedding <=> :q LIMIT k` after filtering by `document_id`.
Consequences: perfect recall and no index maintenance. Must be revisited if cross-document search is added.
Alternatives: HNSW or IVFFlat now (no speed benefit at this size, lower recall with selective filters).

## ADR-010: AGENTS.md as the single source of agent instructions

Context: the owner will use Claude Code, Cursor and Codex, and wants consistent results.
Decision: all rules live in `AGENTS.md` and `docs/`; `CLAUDE.md` imports it and `.cursor/rules/` points to it.
Consequences: one place to edit; any agent that reads `AGENTS.md` follows the same rules. Agents still differ in quality, so `make check` and the evals are the shared referee.
Alternatives: separate rule files per tool (they drift apart).

## ADR-011: Pinned dependencies

Context: different agents and machines must produce the same environment.
Decision: in Sprint 1, adopt a lock file for the backend (uv or pip-tools) and commit `package-lock.json` for the frontend; CI installs from the lock files.
Consequences: reproducible builds; dependency updates become deliberate (Dependabot pull requests).
Alternatives: lower-bound ranges only (current Sprint 0 state; acceptable only until the lock file lands).

## ADR-012: Production database is a managed Postgres with pgvector

Context: free web-host databases may expire or lack the extension, and the owner already works with Supabase.
Decision: use Supabase or Neon (both offer pgvector) as plain Postgres. The app does not use their auth or client libraries.
Consequences: connection settings through `DATABASE_URL`; check pooled versus direct connection behavior with asyncpg during the Sprint 4 deploy test, and check current free-tier limits before relying on them.
Alternatives: Postgres on the app host (simplest, check retention and backup terms).

## ADR-013: Alembic for schema migrations

Date: 2026-10-30
Context: the schema grows every sprint and must be reproducible on a fresh database locally, in CI and in production. Production data cannot be recreated by dropping tables.
Decision: add `alembic` (the migration tool made by the SQLAlchemy author). Each schema change is a numbered Python file in `backend/alembic/versions/` with an `upgrade` and a `downgrade`. `make migrate` applies them.
Consequences: the database history is in git and reviewable. A fresh database reaches the current schema with one command. One more dependency to keep updated (Dependabot covers it). No second database driver is needed, because the Alembic environment runs on the same asyncpg engine as the app.
Alternatives: `Base.metadata.create_all()` at startup (cannot change an existing table, no history), hand-run SQL scripts (no record of which ones ran), another migration tool (less common with SQLAlchemy, no benefit here).

## ADR-014: How the first migration is written (2026-10-30)

Context: S1-1 creates `users`, `refresh_tokens` and `audit_events`. Several choices are not obvious from the code, and the owner must be able to explain them.
Decision:
- The migration is written by hand from `docs/database.md`, not autogenerated. Autogenerate does not reliably handle expression indexes (`lower(email)`) or CHECK constraints, and both are used here.
- `alembic/env.py` is the async template from the installed Alembic. It takes the database URL from the Alembic config if one is set (tests do this), otherwise from `app/core/config.py`, so the app stays the only place that reads environment variables. It uses `NullPool` because a migration run is short.
- Constraint names follow the names PostgreSQL would generate (`users_pkey`, `refresh_tokens_user_id_fkey`, `users_role_check`). The models use the same naming convention, so models and migration agree and a later `ALTER` can refer to a constraint by a predictable name.
- The column `audit_events.metadata` is mapped to the attribute `event_metadata`, because `metadata` is reserved on SQLAlchemy models.
- `AuditEvent` lives in `app/modules/auth/models.py` for now. `docs/architecture.md` has no audit module, and every Sprint 1 audit event is an auth event. Move it when a second module writes audit events.
- The `vector` extension is not created here. It belongs to the Sprint 2 migration, the first one that uses `vector(384)`. Locally `infra/db/init/001_extensions.sql` already creates it.
Consequences: more typing than autogenerate, in exchange for exact control. Anyone changing a model must also write a migration by hand and update `docs/database.md`.
Alternatives: autogenerate then edit (the output for partial and expression indexes needs checking line by line anyway), one `Base.metadata.create_all` for tests (hides migration mistakes).

## ADR-015: Migration tests use a throwaway database (2026-10-30)

Context: a migration test must apply every migration to an empty database and then undo them. Doing that on the development database would delete its tables.
Decision: each migration test creates a database named `gaplens_test_<random>`, runs Alembic against it, and drops it afterwards. The Alembic command runs in a worker thread because its async environment starts its own event loop.
Consequences: tests need a running Postgres (`make up` locally, a service container in CI) and the database user must be allowed to create databases. The development database is never touched. The tests prove the migrations work from zero, which is the S1-1 acceptance criterion.
Alternatives: a fixed shared test database (tests could collide and leave state behind), SQLite (different SQL, no `lower()` index or pgvector behavior, and `AGENTS.md` requires real Postgres).

## ADR-016: argon2-cffi for password hashing

Date: 2026-10-30
Context: passwords must be stored so that a leaked database does not reveal them. A fast hash such as SHA-256 lets an attacker try billions of guesses per second.
Decision: add `argon2-cffi` and hash with its `PasswordHasher` defaults, which are argon2id (the variant `docs/security.md` requires) with 64 MiB of memory, 3 passes and 4 lanes. Each hash gets a random salt and the result is one self-describing string, so parameters can change later without a migration.
Consequences: one hash costs tens of milliseconds of CPU and 64 MiB of memory, which is the point. It must run off the event loop. The real timing on the deploy instance is checked in Sprint 4, as `docs/security.md` says, and the parameters are tuned only if it is far from 50 to 100 ms.
Alternatives: bcrypt (older, 72-byte password limit, not memory-hard), scrypt in the standard library (memory-hard, but the parameters and encoding would be ours to get right), SHA-256 with a salt (far too fast).

## ADR-017: email-validator for email addresses

Date: 2026-10-30
Context: registration needs to reject malformed email addresses before they reach the database.
Decision: depend on `pydantic[email]`, which installs `email-validator`, and use Pydantic's `EmailStr`. We lowercase and trim in our own validator because the library only normalizes the domain part.
Consequences: a well-tested rule instead of our own pattern, and it also enforces the 254-character limit that matches the CHECK constraint on `users.email`. It checks syntax only. It does not check that the mailbox exists.
Alternatives: a hand-written regular expression (accepts some invalid addresses, rejects some valid ones, and we would own every edge case).

## ADR-018: How register is built (2026-10-30)

Context: S1-2 is the first endpoint, and its choices set patterns for the rest of the API.
Decision:
- The service inserts and lets the unique index `users_email_lower_uidx` reject duplicates. It recognises that case by the index name carried on the driver's exception, not by message text. Checking for the email first and inserting second has a race: two simultaneous requests can both pass the check. A test sends five at once and expects exactly one user.
- Any other integrity error is re-raised and becomes a generic 500, not a false "email already registered".
- Hashing runs in a worker thread through `run_in_threadpool`, so one slow hash does not block other requests.
- Errors use the format in `docs/api.md`, built in one place (`app/core/errors.py`). Services raise `DomainError` subclasses and never build responses. The validation handler returns only the field name and the message, never the submitted value, because the value may be a password.
- The request id is stored on `request.state` as well as in the context variable. The handler for unexpected errors runs outside the request id middleware, where the context variable has already been reset.
- The database engine sets `hide_parameters=True`. Without it, SQLAlchemy puts the bound values (an email, a password hash) into error messages that could reach the logs.
Consequences: the register rate limit (5 per hour per IP) arrives with `slowapi` in S1-3, and the `auth.register` audit event in S1-6, both as named in `docs/sprints.md`. Until S1-3 the endpoint has no rate limit.
Alternatives: a pre-check query before the insert (race), matching on the error message text (breaks if the database language changes), catching every `IntegrityError` as a duplicate (hides real faults).

## ADR-019: PyJWT for access tokens

Date: 2026-10-30
Context: after login the client needs a short-lived proof of identity that the server can check without a database lookup on every request.
Decision: add `PyJWT` and sign access tokens with HS256 using a secret from `JWT_SECRET`. Claims are `sub`, `role`, `iat`, `exp`, `iss` and `aud`, as in `docs/security.md`. `JWT_SECRET` has no default and must be at least 32 characters, so the app cannot start with a guessable key. Only issuing is built in S1-3. Verification, which must pass the allowed algorithm list explicitly and require `exp`, `iss` and `aud`, comes with `/auth/me` in S1-5.
Consequences: a stolen access token works until it expires (15 minutes) and cannot be revoked early, which is why it is short-lived and kept in memory on the client. One shared secret means whoever holds it can mint tokens for anyone, so it lives only in environment variables. Rotating it logs everyone out.
Alternatives: server-side sessions in the database (revocable, but a lookup on every request), `python-jose` or `authlib` (larger or less maintained for this need), RS256 asymmetric keys (useful when other services verify tokens, which is not the case here).

## ADR-020: slowapi for IP rate limits, `limits` for the per-email limit

Date: 2026-10-30
Context: `docs/security.md` asks for login limits per IP and per email, and limits on other endpoints later.
Decision: add `slowapi`, which is in the fixed stack, for per-IP limits as a decorator on each route, with a moving window. The per-email limit cannot use slowapi, because its key function only sees the request and not the JSON body. It uses the `limits` library directly (slowapi is built on it), through a small `EmailFailureLimiter` class. `limits` is listed as its own dependency because the code imports it. Counters are in memory, as accepted in `docs/security.md`.
Consequences: limits reset when the API restarts and are per instance, so with more than one instance they must move to Postgres or Redis. Behind a proxy the client IP is the proxy's until forwarded headers are trusted from the platform only, which is a Sprint 4 deploy task. Tests reset the counters between tests.
Alternatives: writing all limits by hand (more code to explain), a Redis-backed limiter now (a new service for one instance), limiting by IP only (does not stop one account being attacked from many addresses).

## ADR-021: How login is built (2026-10-30)

Context: S1-3 is the core of authentication, so each choice below is one the owner must be able to explain.
Decision:
- A wrong password, an unknown email and a disabled account return the same `401 invalid_credentials`. For an unknown email the service still verifies the submitted password against a fixed dummy hash, so the response takes about as long and timing does not reveal which emails have accounts. A test checks that the verification runs.
- The email limit counts failures only, and checks with `test()` before verifying, which does not use up an attempt. A person who logs in correctly is never locked out by their own logins. The cost is that a blocked email stays blocked even for the correct password until the window passes. The email is counted as submitted, whether or not an account exists.
- The refresh token is 256 random bits from `secrets.token_urlsafe(32)`. The database stores only its SHA-256. Plain SHA-256 is right here, unlike for passwords, because the input cannot be guessed, and lookups need a fast, repeatable hash.
- Every login starts a new `family_id`. Rotation in S1-4 keeps all tokens of one login in the same family, so reuse of an old token can revoke exactly that login.
- The refresh cookie is `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`, so scripts cannot read it, it only travels over HTTPS, it is never sent from another site, and it is only sent to the auth endpoints.
- The login password has no minimum length but a maximum of 128, so a request cannot make the server hash a huge string.
- Not built yet: refresh and rotation (S1-4), access token verification (S1-5), audit events (S1-6). Rehash-on-login when the hashing parameters change is not built, because they have never changed.
Consequences: the login endpoint's response time is dominated by one argon2 verification, on purpose. The rate limits can lock a real user out for a short time if someone else keeps guessing their email.
Alternatives: different errors for each failure (lets attackers list accounts), counting all attempts toward the email limit (locks out real users), returning the refresh token in the body (readable by scripts), storing the refresh token unhashed (a database leak would then hand out sessions).

## ADR-022: How refresh rotation works (2026-10-30)

Context: S1-4 keeps users signed in by swapping the refresh cookie for a new pair, and has to notice when a copied refresh token is used. It is the part of authentication most likely to be asked about in an interview.
Decision:
- Rotation: each refresh revokes the presented token and issues a new one in the same family (the family is one login). The old row's `replaced_by` points at the new row, so the chain is traceable.
- The old token is claimed with one atomic `UPDATE ... WHERE token_hash = ? AND revoked_at IS NULL AND expires_at > now RETURNING ...`. When two requests present the same token at once, the database lets only one change the row. A "read the token, then revoke it" sequence would let both succeed. A test sends two at once and expects exactly one 200.
- If the claim finds nothing, a second lookup separates the cases. A token that exists and is already revoked is being used a second time, so every token of its family is revoked. An unknown or merely expired token only gets the 401. The family revocation is committed before the error is raised, because raising rolls the transaction back.
- Every failure (missing, unknown, expired, reused, disabled user) returns the same `401 invalid_refresh_token` and clears the cookie, so the response never says which one it was. A disabled user also loses the whole family.
- The `Origin` check is a route dependency, so it runs before any token is looked at. A request from a wrong origin gets `403 origin_not_allowed` and cannot use up a token. A missing `Origin` is rejected, because browsers always send it on a POST, so only a script lacks it. The allowed list is the existing `CORS_ORIGINS` setting, compared exactly.
- Reuse detection is strict, as in `docs/security.md`. There is no grace window.
- The `auth.refresh_reuse_detected` audit event is not written yet. The audit helper arrives in S1-6, which now lists this event.
Consequences:
- Two browser tabs that refresh in the same instant look like theft and sign the user out. The frontend (S1-7) can reduce this by sending only one refresh at a time, and the rule can be revisited with real use. A short grace window would remove the problem but would also stop detecting a thief who uses a stolen token inside it.
- Each rotation gives the new token a fresh 7 days, so a user who keeps using the app stays signed in indefinitely. A fixed maximum age for one login would need a new column, so it is not built.
- Both new hot-path queries use existing indexes. On a throwaway table of 50,000 rows, `EXPLAIN (ANALYZE, BUFFERS)` showed an index scan on `refresh_tokens_token_hash_uidx` for the claim (0.14 ms) and the reuse lookup (0.02 ms), and a bitmap scan on `refresh_tokens_family_id_idx` for the family revoke (0.11 ms).
Alternatives: read then update in two steps (race), a grace window for recent rotations (weaker theft detection), different errors per failure (leaks which case happened), checking the origin inside the service (runs after the token has been touched).

## ADR-023: How access tokens are verified and how logout works (2026-10-30)

Context: S1-5 adds the first endpoint that needs a signed-in user (`/auth/me`) and the logout endpoint. Verifying a token wrongly is the classic way JWT systems get broken, so each rule below is one the owner must be able to explain.
Decision:
- `verify_access_token` passes the allowed algorithm (`HS256`) explicitly to the library. If it did not, the token's own header would pick the algorithm, which is how an `alg: none` token (no signature at all) gets accepted. It also requires `exp`, `iat`, `iss`, `aud` and `sub`, because a token with no `exp` would never expire. Issuer and audience must match our settings. Any failure, including a malformed token or a `sub` that is not a UUID, becomes one `InvalidAccessTokenError`.
- The token is trusted only to say who the user is. `get_current_user` loads the user from the database on every request and rejects a deleted or disabled one. This costs one primary-key lookup per request, and in return disabling an account works at once instead of after 15 minutes. The role comes from the database too, so a token cannot claim a role.
- A missing header, another scheme, and every kind of bad token return the same `401 invalid_access_token` with `WWW-Authenticate: Bearer`.
- Logout revokes the whole family of the cookie's token with one statement, so it works even if the cookie holds an old, already-rotated token, and one logout ends exactly one login. It is quiet: a missing, unknown or already-revoked cookie still gets `204` and a clearing `Set-Cookie`, so a second logout is harmless and the response says nothing about the token. It uses the same `Origin` dependency as refresh, which runs before any token is touched.
- On a 50,000-row table, `EXPLAIN (ANALYZE, BUFFERS)` of the logout statement showed an index scan on `refresh_tokens_token_hash_uidx` for the lookup and a bitmap scan on `refresh_tokens_family_id_idx` for the update, 0.16 ms in total.
Consequences: logout cannot cancel an access token that was already issued, because access tokens are stateless. It works until it expires, at most 15 minutes, which is why it is short-lived and why the client drops it from memory on logout. A general per-user rate limit for `me` and `logout` (the "everything else" row in `docs/security.md`) is not built yet. The `auth.logout` audit event arrives in S1-6.
Alternatives: trusting the role claim (saves a query, but a stolen or stale token keeps old privileges), a server-side list of revoked access tokens (makes every request depend on it), revoking only the presented refresh token on logout (an older copy in the same login would still work), returning `401` on logout without a cookie (leaks nothing but makes a double logout look like a failure).

## ADR-024: How auth audit events are written (2026-10-31)

Context: S1-6 records who did what, so that an attack or a stolen account can be investigated afterwards. The same table is also a place where personal data could leak, so what goes in it matters as much as that it exists.
Decision:
- Five events: `auth.register`, `auth.login`, `auth.login_failed`, `auth.logout` and `auth.refresh_reuse_detected`, written by the auth service through one helper (`modules/auth/audit.py`). The helper adds the row to the caller's transaction and the caller commits, so a row exists if and only if the action it describes happened. A test makes the audit insert fail and checks that no user or token was created.
- For failures the event must be committed before the error is raised, because raising rolls the transaction back. This is the same reason as the family revocation in ADR-022. Two mutation checks showed the tests catch a missing commit in both places.
- A failed login stores a SHA-256 of the submitted email, not the email, plus a `reason` (`unknown_email`, `wrong_password`, `account_disabled`). The digest lets repeated attempts on one address be matched without keeping personal data, and it also covers a password typed into the email box by mistake. The reason is kept in the database only and is never in a response, so it does not weaken the same-response rule from ADR-021. All three failure kinds do one insert and one commit, so the timing protection from ADR-021 still holds.
- Requests blocked by the email rate limit write nothing. Otherwise an attacker could grow the table, and the audit trail would fill with noise, faster than the rate limits allow.
- Logout is recorded only when it ended a login. The revoke statement now returns the owner's user id, and no row means nothing was ended, so a repeated logout writes nothing.
- Token reuse is recorded against the login it revoked (`resource_type = refresh_token_family`, `resource_id` = the family), with the token's owner as the actor. An unknown or expired token writes nothing, because that is not evidence of theft.
- The request id and IP are the same values already in the logs and in the refresh token rows.
Consequences:
- A stale cookie presented after a normal logout counts as reuse and writes a `auth.refresh_reuse_detected` row, even though no theft happened. The browser drops the cookie when logout clears it, so this should be rare, but the event means "a revoked token was presented", not proof of theft.
- Every auth action now does one more insert. This is negligible next to the argon2 hash.
- The database role that can only INSERT and SELECT on `audit_events`, the one-year retention purge, and any way to read the events are not built. The first belongs to the Sprint 4 deploy set-up, and a reader would be an admin dashboard, which is a non-goal.
- `AuditEvent` stays in the auth module for now (ADR-014) and moves when the first non-auth event, `document.upload`, arrives in Sprint 2.
Alternatives: storing the readable email on failed logins (useful for investigations, but it keeps personal data for a year and can hold a typed password), recording blocked attempts (an attacker-controlled write rate), writing the event in a separate transaction (a crash could leave the action done and unrecorded, or recorded and not done).

## ADR-025: The frontend stack and the versions installed (2026-10-31)

Context: S1-7 starts the frontend. `AGENTS.md` fixes the stack; this records what that means in versions, and the two places where the newest release could not be used.
Decision: the versions below were read from the npm registry on 2026-10-31 and are locked in `frontend/package-lock.json`, which CI installs with `npm ci`.

| Area | Packages (major.minor installed) |
|---|---|
| Runtime and build | Node 22 (`.nvmrc`, `engines ^22.22.2`), React 19.3, Vite 8.3 with `@vitejs/plugin-react` 6.1 |
| Language and lint | TypeScript 6.0 (strict), ESLint 10.14 with `typescript-eslint` 8.72 and `eslint-plugin-react-hooks` 7.1, Prettier 3.9 |
| Styling and UI | Tailwind CSS 4.3 with `@tailwindcss/vite`, shadcn/ui (CLI 4.23, style `new-york`, `radix-ui` 1.8), `lucide-react` 1.65, `@fontsource` IBM Plex Sans and Mono |
| Data and routing | TanStack Query 5.105, `react-router` 8.5, Zustand 5.0 |
| Forms | React Hook Form 7.91, `@hookform/resolvers` 6.0, Zod 4.6 |
| Tests | Vitest 5.0, Testing Library (react 16.3, dom 10.4, jest-dom 7.0, user-event 14.6), jsdom 30 |

- TypeScript is pinned to 6.0 (`~6.0.3`), not the 7.0 that the registry offers. `typescript-eslint` 8.72 supports TypeScript below 6.1, so 7.0 would break linting. Revisit when `typescript-eslint` supports 7; if Dependabot proposes the upgrade before then, it should not be merged.
- The router is the `react-router` package, version 8. The separate `react-router-dom` package is the older 7 line. React Router 8 and jsdom 30 need Node 22.22 or newer, which sets the `engines` range.
- Only the five shadcn components the first screens need are added (Button, Input, Label, Form, Skeleton). The generated files are changed only to follow `docs/design-system.md`.
- Not added: a network-mocking library (tests stub `fetch` with a small helper, so tests stay close to the one place that calls it), and an accessibility lint plugin (the form tests check labels, error links and roles directly; revisit in S4-5).
Consequences: more dependencies than the backend, so Dependabot weekly updates matter here; `npm audit` runs in CI as advisory and becomes blocking in Sprint 4. The production bundle is 528 kB (164 kB compressed), above Vite's 500 kB warning, which is acceptable now and is handled by route-level code splitting when more screens exist.
Alternatives: Material UI (ADR-005), `react-router-dom` 7 (older line), TypeScript 7 now (breaks the linter), Jest instead of Vitest (a second build pipeline), `localStorage` persistence for the session (ADR-008 and `docs/security.md` rule it out).

## ADR-026: How the frontend keeps the session (2026-10-31)

Context: the backend hands out a 15-minute access token and a rotating refresh cookie, and treats a second use of an old refresh cookie as theft (ADR-022). The frontend has to keep the user signed in across reloads without ever making that happen by accident.
Decision:
- The access token lives only in a Zustand store in memory. Nothing is written to `localStorage`, `sessionStorage` or a script-readable cookie, a test checks this, and ESLint forbids those globals. A reload loses the token on purpose and the refresh cookie gets a new one.
- The signed-in user is kept in the TanStack Query cache, seeded from the login and refresh responses, not in Zustand, because `AGENTS.md` says not to mirror server data there.
- `src/lib/api.ts` is the only place that calls `fetch` (ESLint enforces it). It adds the bearer token, turns the error format from `docs/api.md` into an `ApiError`, validates success bodies with Zod, and on a `401 invalid_access_token` refreshes once and retries once. It talks to the session through a small "port" so it does not import from the auth feature.
- Refreshing is single-flight per tab, and the refresh request also takes a Web Lock shared by all tabs of the browser. Reason: React's development mode runs effects twice, and two tabs reloading together do the same, and either case would send the same cookie twice at once, which the backend reads as theft and answers by ending the login. One shared request, and tabs taking turns so the second one sends the cookie the first one just received, remove that. Where the Web Locks API is missing, the per-tab protection still applies.
- On start the app asks for a session. While it waits the guarded pages show a loading skeleton, and neither redirects, so a reload on a page keeps that page. No session is the normal case for a new visitor, so a failed restore shows no error.
- Sign-out always ends the session on this device, even if the request to the server fails, and clears the cached data so the next person on the browser sees nothing of it.
- Register is two requests, register then login, because the API returns no tokens from register. If the login after a successful register fails, the form says the account exists and asks the user to sign in.
Consequences:
- If the server cannot be reached at sign-out, the refresh cookie stays valid on the server and in the browser, so the next page load signs the user in again. The user sees them signed out and can retry, but it is a real gap, and it is not hidden.
- A refresh that fails because of a network problem is treated as "no session", so a temporary outage on reload shows the login page. Signing in again fixes it.
- A wrong `CORS_ORIGINS` makes every refresh fail with `origin_not_allowed`, which looks like "reload signs me out". The development origin is `http://localhost:5173`, which is the backend default.
Alternatives: token in `localStorage` (readable by any script that runs on the page), refreshing on a timer (extra requests and the same race), one refresh per failed request without sharing (the race), a polling "is the other tab done" flag instead of a lock (can still race).

## ADR-027: Backend lock files with pip-tools and hashes (2026-10-31)

Context: ADR-011 asked for a backend lock file in Sprint 1. Until now `pyproject.toml` held only lower bounds, so CI, `make install` and the Docker image each resolved fresh versions, and a bad or tampered release could reach `main` without any change in the repository.
Decision:
- `backend/pyproject.toml` stays the file a person edits. `make lock` runs `pip-compile --generate-hashes` and writes `backend/requirements.txt` (runtime) and `backend/requirements-dev.txt` (runtime plus dev). They are generated and never edited by hand.
- Every install uses them: `pip install --require-hashes -r ...` for third-party packages. `make install` and CI then install our own package with `--no-deps --no-build-isolation`, so the build uses the `setuptools` pinned in the lock instead of fetching an unchecked one. The Dockerfile installs the runtime file only (no test tools) and does not pip-install our code at all; uvicorn and alembic run from `/srv`. With hashes, pip refuses a file whose bytes differ from what was recorded.
- The lock is generated with `--allow-unsafe`, which also pins `pip` and `setuptools`. Without it, a fresh environment fails with "all requirements must have their versions pinned" (found by installing into an empty venv).
- CI regenerates the lock and fails if it changes, so editing `pyproject.toml` without running `make lock` is caught. `pip-compile` keeps existing pins unless asked to upgrade, so the check does not fail just because a new release appeared.
- The files are named `requirements*.txt` so Dependabot's pip updater recognizes them and proposes version bumps as pull requests. Upgrading is then a reviewed change.
- `pip-audit` in CI now audits the dev lock file, which is what is actually installed. It stays advisory until Sprint 4.
- Dependencies added: `pip-tools` (lock generation) and `pre-commit` (ADR-028), both dev only.
Consequences: builds are reproducible and a tampered package fails loudly. The cost is a second step after changing dependencies (`make lock`), and the hashes are produced for Python 3.12 on Linux, which is what CI and the image use; a developer on another platform still installs, because pip-compile records hashes for all published files of each version.
Alternatives: uv with `uv.lock` (faster and one tool, but it replaces the venv, install and CI steps in one go and adds a tool to explain; revisit if install time becomes a problem), pinning `==` in `pyproject.toml` by hand (no hashes, no transitive pins), Poetry (a different project layout).

## ADR-028: Secret scanning with gitleaks, in pre-commit and in CI (2026-10-31)

Context: `docs/security.md` requires a secret scanner as a pre-commit hook and a CI step. A secret that reaches a public repository must be treated as leaked even if the commit is deleted later, so catching it before the commit matters most, and history must be scanned too.
Decision:
- Pre-commit: the `pre-commit` framework runs the gitleaks hook, pinned in `.pre-commit-config.yaml` to release `v8.30.1`. `make hooks` installs it once per clone. The hook scans staged changes only, so it is fast.
- CI: a separate `secrets` job checks out the full history (`fetch-depth: 0`), downloads the pinned gitleaks release, checks its sha256 against a value written in the workflow, and runs `gitleaks git --redact`. `--redact` keeps any match out of the public log. CI is the backstop when someone commits with `--no-verify`.
- The gitleaks binary is used directly, not `gitleaks-action`: the action needs a license for organization accounts and would be one more third-party action running with the repository token.
- Default gitleaks rules. Exceptions are added only for a specific string, never for a whole path.
Consequences: a leaked key is blocked at commit time and again in CI. The scanner finds patterns, so a weak password with no recognizable shape can still pass; the rule "never commit `.env`" stays in force. A hook is only active after `make hooks`, which is why CI scans too. When bumping gitleaks, update the version in `.pre-commit-config.yaml` and the version and checksum in the workflow together.
Alternatives: GitHub secret scanning push protection alone (works only on the host, gives no local feedback, and its coverage depends on the plan), `detect-secrets` (baseline file to maintain), a hand-written git hook script (more code to own, no pinned version).

## ADR-029: pgvector for the vector column, and how the document tables are built (2026-10-31)

Context: S2-1 adds `documents` and `document_chunks`. The chunks table has a `vector(384)` column, and SQLAlchemy has no built-in type for it. S2-5 and S2-6 also need the driver to send and read vectors.
Decision:
- Add the `pgvector` Python package (the official client for the extension). It provides the `Vector(384)` column type used by the model and the migration. Sprint 2 later registers its asyncpg codec on the engine. It imports `numpy` only when a numpy array is passed, so plain Python lists work and numpy is not installed.
- The migration runs `CREATE EXTENSION IF NOT EXISTS vector` itself (ADR-014 left this to the first migration that uses the type). The Compose init script only covers the default database, and the migration tests create a fresh database for every test. The extension is not marked trusted, so the role that runs migrations must be allowed to create it. On a managed host (Supabase, Neon) check this during the Sprint 4 deploy; if the role cannot, enable the extension once from the host's dashboard and the `IF NOT EXISTS` makes the migration a no-op.
- `downgrade` drops only the two tables and leaves the extension, because other databases and the init script rely on it. It deletes all documents and chunks, and a comment in the migration says so.
- The duplicate-upload rule and the document list use partial indexes (`WHERE deleted_at IS NULL`), so a soft-deleted document does not block re-uploading the same file and does not slow the list. Tests prove both.
- `sha256` is `char(64)`: a SHA-256 in hex is always 64 characters, and the type states it.
- `owner_id` is repeated on `document_chunks` as in `docs/database.md`, so every retrieval query filters on it directly. Nothing in the database forces it to equal the owner of the document, so the code that inserts chunks (S2-5) must copy it from the document.
- Both models live in `app/modules/documents/models.py`, because `docs/architecture.md` gives `ingestion` no models file. `alembic/env.py` imports the module so the tables register on the shared metadata.
- A test compares the models with the migrated database using Alembic's `compare_metadata`. A mutation check (changing a nullability and an index uniqueness in the model) made it fail. It does not reliably see changes to a partial index's `WHERE` clause or to a CHECK expression, so those are covered by the behavior tests (duplicate, soft delete, bad status, zero size, empty title, negative index, wrong vector size, cascades).
Consequences: one more dependency, locked with hashes in the existing lock files. Chunks cannot hold a vector of the wrong size. Chat and `llm_calls` tables are not here; they arrive with S2-7 in their own migration.
Alternatives: a small hand-written `UserDefinedType` for `vector(384)` (no dependency, but S2-5 and S2-6 would need hand-written encoding and casts), a database trigger or composite foreign key to force the chunk owner to equal the document owner (stronger, but not in `docs/database.md` and it would complicate the insert).

## ADR-030: pypdf and python-multipart (2026-10-31)

Context: S2-2 reads PDFs and receives file uploads. Neither capability is in the standard library or in FastAPI itself.
Decision:
- Add `pypdf` (already named in the fixed stack in `AGENTS.md`) to open a PDF, see whether it is encrypted, count pages and pull out text. It is pure Python, so the image needs no system packages.
- Add `python-multipart`, which FastAPI requires to read `multipart/form-data`. Without it a route with a file parameter fails at startup.
Consequences: both are locked with hashes (ADR-027). pypdf parses untrusted bytes, so a parser bug is a real risk. The caps (5 MiB, 100 pages, 300,000 characters) and the worker thread reduce it, and ADR-031 says what is still open.
Alternatives: PyMuPDF (faster, but a C library with a copyleft licence and a heavier image), pdfminer.six (more code to get page-by-page text), accepting only text files (rejects the documents consultants actually receive).

## ADR-031: How upload validation works (2026-10-31)

Context: S2-2 is the first place that handles a hostile file. Each rule below is one the owner must be able to explain.
Decision:
- The file type comes from the bytes. `%PDF-` at the start means PDF. Anything else must decode as strict UTF-8 and contain no NUL byte, otherwise `415`. A PNG named `report.pdf` is rejected; a PDF named `notes.txt` is treated as a PDF. The client's content type is ignored. Markdown cannot be told from plain text by bytes, so a `.md` or `.markdown` name only chooses the label `text/markdown`; it can never make a file acceptable.
- The checks run in this order, cheapest first: size, type, then for a PDF: can it be opened, is it encrypted, page count (before any text is read), extracted characters (stopping the moment the cap is passed), any text at all. A large document therefore costs almost nothing to refuse.
- Text checks happen in the upload request, in a worker thread (`run_in_threadpool`), so the user gets an immediate, specific error instead of a document that later fails. This parses a PDF once for validation; ingestion (S2-3, S2-5) will parse it again from the same bytes, bounded by the same caps. The cost is accepted to keep errors immediate.
- Any encryption is refused, even with an empty user password, as `docs/security.md` says. Any exception from the parser becomes `pdf_unreadable`; only the exception type is logged, because its message can quote the file.
- Duplicates are decided by the unique index, not a prior lookup (the same race as email in ADR-018). The index name is read from the driver's exception.
- The filename is display text. Directory parts from either separator and control characters are removed, `.` and `..` are replaced, and it is cut to 255 characters. It is never used as a path, and the original file is never written to disk by our code.
- `Content-Length` is checked by a small ASGI middleware before the body is read. Starlette spools the whole multipart body before the route runs, so a size check in the route alone would let a huge upload be buffered first. It is limit plus 64 KiB for multipart framing. A client that sends no `Content-Length` (chunked) is not stopped by this; counting the stream was left out because FastAPI turns an exception raised while reading the body into a generic 4xx, which would need response rewriting. The host's request limit is the control for that case, set up in Sprint 4. The route still reads at most the cap plus one byte from the spooled file.
- The upload limit is 10 per hour per user (`docs/security.md`). slowapi's key function decodes the bearer token itself, because the limit runs before the route's own dependency. A request without a valid token is keyed by IP and then gets `401`.
- The audit event `document.upload` is written in the same transaction as the insert. This is the first non-auth event, so as ADR-024 said, `AuditEvent` and `record_audit_event` moved from the auth module into `app/modules/audit/`. Auth keeps its own action names and `email_digest`. The move changed no behavior; the audit tests are unchanged apart from the module they patch.
Consequences:
- Not isolated: a malformed PDF could still make pypdf slow or memory hungry inside the caps, in the API process. The request is bounded by the 5 MiB limit, but there is no timeout on parsing. Sprint 4 decides whether to move parsing to a subprocess with a timeout.
- A user who is rate limited still counts rejected files. That is intended: rejected files cost parsing time too.
- Until S2-5, an uploaded document stays at `uploaded` and nothing keeps its text.
Alternatives: trusting the extension or the content type (trivially spoofed), validating in the background and marking the document failed (the error would no longer be immediate and a hostile file would still be stored), a lookup before insert for duplicates (race), a streaming body counter (see above), storing the file so ingestion needs no second parse (ADR-006 says no).

## ADR-032: How text is extracted and sections are found (2026-11-01)

Context: S2-3 turns the bytes of a validated upload into an ordered list of sections with labels, headings and page numbers. The chunker (S2-4) and the citations built on top of it depend on getting this right, and the input is untrusted and messy: PDFs wrap lines, repeat page headers, and contain numbers at the start of lines that are not clause numbers.
Decision:
- Two small pure modules, no I/O: `extract.py` (bytes to clean pages) and `structure.py` (pages to sections). `extract_document(data, mime_type)` chains them. Nothing calls it yet; the background pipeline (S2-5) will, in a worker thread. The pages of a PDF are numbered from 1. Text and Markdown have no pages, so their page is `None`.
- Normalization is NFKC plus removal of control and format characters (zero-width spaces, soft hyphens, the byte order mark), one kind of line break, collapsed spaces and blank lines. NFKC makes a ligature, a full-width digit or a non-breaking space compare the way a person reads it, which matters when a quote is later matched against stored text. It can change the length of a text (a ligature becomes two letters), so the stored text may be slightly longer than the length checked at upload; the cap exists to keep a document inside one LLM call and has margin.
- A repeated header or footer is a line at the edge of a page (the first two or last two non-empty lines) that appears on more than half of the pages, in PDFs of three or more pages. Only page-number lines ("Page 2 of 9", "- 3 -", "4/12") have their digits folded before comparing. A first version folded digits on every line and wrongly treated "Body of page 1", "Body of page 2" as one footer, which a test showed; every other line is compared exactly.
- A line starts a section if it begins with a clause number (up to three digits per part, so a year is not a number) followed by text that starts with an uppercase letter, or, in a Markdown file only, if it is a heading outside a code fence. The uppercase rule is the main protection against wrapped PDF lines such as "5 percent of tickets..." or "1.5 million users...". The cost is that a real clause that starts in lowercase is read as a continuation of the line above.
- The `heading` of a clause is the title of the closest enclosing section. A Markdown heading is always a title. A numbered line is a title only if it has no text of its own, is at most 10 words with no sentence ending, and is directly followed by one of its sub-clauses. A wrapped sentence such as "3.1 L1 agents may approve refunds up to INR 5,000 per" followed by "request..." is therefore never split into a "heading" and a body. Titles are context only and are not sections, because the chunker embeds `heading + content`. A heading with nothing under it is kept as a section whose text is the title, so no words are dropped (a test checks every word of the sample SOP survives).
- If no clause numbers and no headings are found, the text is split into paragraphs on blank lines, with `structured = False`. The chunker uses the flag to choose the sliding window.
- The extracted text is handed on as data. Nothing in this module interprets it; a test confirms an instruction planted in the injection sample comes out verbatim as ordinary clause text.
- Regular expressions are anchored and bounded (three digits per part, no nested open-ended repetition). A test with a 100,000 character line of digits and dots finishes in a few hundredths of a second.
Consequences:
- Heuristics, not understanding. Known misses: lowercase clause starts, hyphenated words broken across lines (not repaired), Setext headings (underlined with `===`), tables, multi-column PDFs read in the order pypdf returns them. The Sprint 4 evals measure whether this hurts retrieval; they are not a guarantee.
- A Markdown file with only a title and prose becomes one large section, which the chunker splits at sentence boundaries.
- The PDF is parsed once more here than at upload (ADR-031 accepted the cost).
Alternatives: asking an LLM to find the sections (cost, non-determinism, and document text would reach a model before any control is applied), a PDF layout library for font-size based headings (heavier dependency, fails on text-only PDFs), treating every numbered line as a heading (splits wrapped sentences), dropping the uppercase rule and tracking the expected next number instead (breaks on documents whose numbering skips or restarts).

## ADR-033: How chunks are made (2026-11-01)

Context: S2-4 turns the sections from S2-3 into the chunks that are embedded, retrieved and quoted. `docs/ai-engineering.md` gives the sizes (merge under 40 tokens up to about 120, split over 400, windows of 300 with 50 overlap) but leaves several details open. Each answer below changes what is stored.
Decision:
- Token count is words times 1.3, rounded up, never below 1 (the table requires more than 0). It is computed in whole numbers, because 10 * 1.3 in floating point is not guaranteed to be exactly 13. It sizes chunks only; billing numbers come from the API's reported usage.
- Only a clause under 40 tokens starts a merge group. Its following siblings are added, whatever their own size, until the group is at 120 tokens or more or the next sibling would take it over 400. Siblings means the same parent label and the same depth, with a depth of at least 2 (`3.1` and `3.2`). A top-level label such as `4` and any unlabeled section are never merged, so a preamble or an introduction stays whole. A clause of 40 tokens or more never starts a group, but it can be taken into one that a short clause started.
- A merged chunk has the range as its label (`3.1-3.3`), the first clause's heading and page, and the clauses as lines of `label text`. S2-3 removed the number from each clause's text, so without the prefix a merged chunk would not say which clause says what, and neither would a quote from it. A chunk of one clause has no prefix; its label is in `section_label`.
- A clause over 400 tokens is cut at sentence ends. A sentence ends at `.`, `!` or `?` followed by whitespace and then a capital letter, digit, quote or bracket, which keeps "approx. five days" together. The pieces are made similar in size (cut at an even share of the total, or earlier if the next sentence would pass 400) so the last piece is not a stub. A single sentence that is over the limit by itself is cut at word boundaries. Every piece keeps the clause's label, heading and start page; the end page is not tracked.
- Text with no structure is cut into windows of whole sentences, up to 300 tokens, and each window starts early enough to repeat at least 50 tokens of the previous one (always moving on by at least one sentence). The window's page is that of its first sentence. Paragraph breaks inside a window become single spaces.
- The sizes are constants in the module, not settings. A change to any of them changes what retrieval finds and needs an eval run (`AGENTS.md`), so it should be a code change that is reviewed, not an environment tweak.
Consequences:
- The sample SOP is made of clauses under 40 tokens, so it becomes seven section-sized chunks (`1.1-1.2`, `2.1-2.2`, `3.1-3.5`, `4.1-4.3`, `5.1-5.4`, `6.1-6.2`, `7.1`) plus the preamble. The two contradicting refund limits (3.1 and 5.3) stay in different chunks. The golden file lists single clauses such as `3.3` in `expected_sections`, so the retrieval eval must treat a range as covering every clause inside it. That matching is not built yet.
- No before and after eval numbers exist: there is no retrieval (S2-6) and no eval runner (S4-1). This chunker is the baseline, and recall@k is first recorded after S2-6. Later changes to the constants are measured against that.
- The upload caps do not bound the number of chunks. A document of tens of thousands of tiny clauses under different parents would give tens of thousands of chunks to embed. S2-5 must reject a document above a chunk limit before embedding.
- Sentence splitting by punctuation is approximate. Text without capitals after full stops, or with unusual abbreviations, is cut at the wrong place or not at all; the word-boundary cut keeps the size limit anyway.
Alternatives: one chunk per clause always (very small chunks embed poorly and lose the surrounding clauses), fixed-size windows for everything (cut clauses in the middle and lose the label), merging clauses of any size across parents (mixes topics), overlap between split pieces of a clause (duplicate text in results, and citations then point at two chunks), a tokenizer for exact counts (a dependency for a sizing estimate).

## ADR-034: fastembed, the model download and what was measured (2026-11-01)

Context: S2-5 turns chunks into vectors. ADR-004 chose `fastembed` with `BAAI/bge-small-en-v1.5`; this records adding it, how the model files get onto a server, and what running it costs.
Decision:
- Add `fastembed` (it brings `onnxruntime`, `numpy`, `tokenizers`, `huggingface-hub`) and list `onnxruntime` as our own dependency because the code imports it. All are locked with hashes (ADR-027).
- The code uses `passage_embed` for document chunks and `query_embed` for questions, the methods the model's documentation requires. The model loads on first use, not at import, so the app and the tests start fast and a missing model fails one document, not the app.
- No telemetry (`AGENTS.md`): onnxruntime can send usage events, so `disable_telemetry_events()` is called before the model loads, and a test checks the order. The package is loaded by name because it ships no type information, which keeps our code strictly typed without adding a mypy exception.
- The Docker image downloads the model while it is built, into `/srv/models`, owned by the app user, and sets `EMBEDDING_MODEL` and `EMBEDDING_CACHE_DIR` for the app. Serving never waits for a download. `HF_HOME` is set into the same folder, because the downloader keeps its own cache and the app user has no home directory; the first build failed with "permission denied" until this was set. The built image loaded the model and produced a normalized 384-dimension vector with the network disabled.
- The vector column needs no extra driver set-up. Tested on a real database: SQLAlchemy's `Vector` type inserts (single and multi-row), compares with `cosine_distance` and reads back over plain asyncpg, so the pgvector asyncpg codec is not registered anywhere. Retrieval (S2-6) can use `Vector.cosine_distance` the same way.
Measured on the development machine (CPU only, one process), not promised for the deploy host:
- Loading the model took 8.6 s the first time including about 7 s of download, and 0.2 s from a local cache. Resident memory went from 108 MB to 310 MB after loading.
- The eight chunks of the sample SOP embedded in 0.23 s. Vectors have length 1.0, so dot product equals cosine similarity as `docs/database.md` assumes. For "What is the refund limit for L1 agents?" the two chunks that hold the contradicting limits ranked first and second (scores 0.81 and 0.79).
- 1000 chunks of about 150 tokens took 62 s (about 16 chunks per second) with a peak memory of 491 MB. That peak is a problem for a 512 MB free tier. Sprint 4 measures it on the real instance and decides between a bigger instance, a smaller batch, or a hosted embedding API behind the same `Embedder` interface (the fallback `docs/sprints.md` already names).
- The image is 727 MB.
Consequences: the model's files are fetched from Hugging Face at build time without a hash check, so a changed upstream file would change the image. Pinning the files by hash is a Sprint 4 supply chain item. Changing the model means a new migration and re-embedding (`docs/database.md`).
Alternatives: sentence-transformers (needs PyTorch, far larger image), downloading at first use (slow first upload, fails on a restricted host), a hosted embedding API (cost, document text sent to a second provider), registering the pgvector asyncpg codec (not needed, as tested).

## ADR-035: How a document is processed after upload (2026-11-01)

Context: S2-5 runs extraction, chunking, embedding and storage after the upload response, and must leave every document in `ready` or `failed`.
Decision:
- FastAPI `BackgroundTasks` (as `docs/architecture.md` says), started by the upload route with the bytes the request already holds. The bytes live in memory only until the task ends (ADR-006), at most 5 MiB per upload in flight. The task opens its own sessions from a session factory that tests replace, so it never touches the development database.
- A document is claimed with one `UPDATE ... WHERE status = 'uploaded' AND deleted_at IS NULL RETURNING id`. If two tasks ever start for the same document, the database lets only one win (the idea of ADR-022). Finishing and failing are guarded by `status = 'processing'`, so a document the sweep has already failed cannot be turned `ready` afterwards, and a deleted document is left alone.
- Chunks and the `ready` status are written in one transaction, so a document is never `ready` with half its chunks. Chunks are inserted in batches of 500 (`docs/database.md`) and `owner_id` is copied from the document, which closes the caveat in ADR-029; a test checks that every chunk belongs to its document's owner.
- Embedding runs on a dedicated single thread. That keeps it off the event loop, and it means only one document is embedded at a time, so CPU and memory stay bounded on a small host while other uploads wait their turn. A thread, unlike a lock or semaphore, is not tied to an event loop. Text goes through the model in batches of 32.
- A document over 1000 chunks (`MAX_CHUNKS_PER_DOCUMENT`) is failed before anything is embedded. This is the guard ADR-033 asked for. At the measured speed (ADR-034) 1000 chunks is about a minute of embedding.
- Failures never leak. The task catches every `Exception`, rolls back, and stores one of four fixed texts in `error_message` (`docs/api.md`). Only the exception's type name and the document id are logged, because an exception message can quote the document. If marking the failure fails (the database is down), the task logs and returns instead of raising, and the sweep fails the document later. A cancelled task (shutdown) is not caught on purpose; the document stays `processing` and the sweep handles it.
- The sweep fails documents in `uploaded` or `processing` whose `updated_at` is older than 15 minutes. `uploaded` is included because that state should last milliseconds, so an old one means the process died between the insert and the task; it also cleans up documents uploaded before this story existed. It runs at start and every 5 minutes from the app lifespan, and the loop is cancelled at shutdown. It is a system job, so it is not scoped to an owner and returns only a count. A database that is down at start is logged, not fatal.
- The upload response is built before the task runs, so it says `uploaded`. In tests the task has finished by the time the request returns, so two existing assertions that read the stored status or compared the full document now expect `ready`; both changes follow from this decision only.
Consequences:
- A restart during processing fails the document after up to 15 minutes plus a sweep interval, not at once. Nothing resumes work: the original file is not kept, so a failed document cannot be retried without a new upload.
- A failed document still holds its `(owner_id, sha256)` slot in the duplicate-upload index, so uploading the same file again is rejected as `duplicate_document` until the failed document is deleted, and the delete endpoint is not built. This needs a decision before the UI: either allow a new upload to replace a failed document of the same file, or build delete first. Not decided here.
- If the server stops between the upload response and the end of the task, the upload is lost. Acceptable for one instance; a job table would fix it if needed (`docs/architecture.md`).
Alternatives: processing inside the request (a 60 second request for a large document), `asyncio.create_task` by hand (no hook for tests and easy to lose), a worker process and job table now (a second service for one instance), a status read-then-write instead of a guarded update (two tasks could both pass the check), a semaphore for one-at-a-time embedding (bound to an event loop).

## ADR-036: Deleting a document (2026-11-01)

Context: ADR-035 left a gap. A failed document keeps its `(owner_id, sha256)` slot in the duplicate-upload index, so the same file could not be uploaded again, and `DELETE /documents/{id}` was not built. `docs/api.md`, `docs/security.md` and `docs/database.md` already described delete; no sprint story owned it, so it was added as S2-5a.
Decision:
- Delete is a soft delete: `deleted_at` is set by one `UPDATE ... WHERE id, owner_id, deleted_at IS NULL RETURNING id`. The partial unique index already leaves out deleted rows, so the file can be uploaded again at once. If the update returns no row the answer is the same `404 document_not_found` as for a missing or foreign id, which also makes a second delete a plain 404 and lets only one of several simultaneous deletes write the audit event.
- The document's chunks are deleted in the same transaction, which is a choice beyond what `docs/database.md` said. That doc purges soft-deleted rows after 30 days, which would leave the document's text in the database for a month after the user deleted it. The chunks are the only place the text lives (the original is never stored, ADR-006), so removing them makes "deleted" mean deleted. The document row keeps its title, hash and metadata (no document text) for the 30-day retention and the audit trail. Later tables that hold text derived from a document (chat messages, findings) will need the same treatment when they are built.
- The `document.delete` audit event is written in the same transaction, like every audit event (ADR-024). A delete that finds nothing writes nothing.
- Deleting works in every status. A document deleted while it is being processed is safe without extra code: the background task's finishing step requires `status = 'processing' AND deleted_at IS NULL`, so it stores nothing (a test proves it). A user can therefore also remove a document that is stuck.
- This resolves the open item in ADR-035. A failed document is removed with delete and its file uploaded again. Replacing a failed document automatically on re-upload was not built; it can be added if people hit the extra step often.
Consequences: until the purge exists (Sprint 4), deleted document rows accumulate without their text. Retrieval and any later query must skip documents with `deleted_at` set, which `get_document` already does. There is no way to restore a deleted document.
Alternatives: keep the chunks until the 30-day purge (the text stays after the user asked for removal), hard delete at once (loses the audit trail's link to the document and frees nothing the soft delete does not), let a new upload replace a failed document (hides a failure and needs more logic in the upload path).

## ADR-037: How retrieval works and what it measured (2026-11-01)

Context: S2-6 finds the chunks of one document that best match a question. Chat (S2-7) builds its answer and its citations from the result, so a wrong or leaked chunk here becomes a wrong or leaked answer.
Decision:
- Two layers. The repository runs one query: cosine distance (`<=>`) to the question's vector, `WHERE document_id = ? AND owner_id = ?`, ordered by distance and then `chunk_index`, limited to k. The score is `1 - distance`, which is the cosine similarity because the vectors have length 1. The service first calls the documents service to check that the document is the user's, not deleted and `ready`, then embeds the question and applies the cutoff.
- Both ids are in the query. `document_id` alone finds the rows, since it is unique, but with `owner_id` too a wrong or forged id can never return another user's text, whatever a caller forgot to check. A test runs the query with the wrong owner and gets nothing; the service raises the same `404` for a foreign, a missing and a deleted document.
- A document that is not `ready` raises `409 document_not_ready` instead of returning nothing. An empty result would make chat answer "not found in the document" for a document that is only still being processed. The error code is added to `docs/api.md` with the chat endpoint that returns it (S2-7).
- The question is embedded on the same single thread that embeds document chunks (ADR-035), so memory stays bounded. A question waits behind at most the 32-chunk batch that is running, a few seconds on the development machine, not behind a whole document.
- `RETRIEVAL_MIN_SCORE = 0.0` means no cutoff. The code applies the cutoff only when it is above 0, so a rare negative cosine score is not dropped by a setting that is switched off. `RETRIEVAL_TOP_K = 6`.
- The vector parameter needs no special driver set-up (ADR-034).
Measured baseline (real model, `python ../evals/retrieval_eval.py`, ten questions on one fictional eight-chunk document, so a baseline and not evidence of general quality): recall@1 0.88, recall@3 1.00, recall@6 1.00, MRR 1.00. Seven questions have expected sections (eight section pairs, because the conflict question needs two). Every question found its section at rank 1 except the conflict question Q1, whose second section (`5.3`, inside chunk `5.1-5.4`) was at rank 2. With eight chunks in total, recall@6 is nearly guaranteed; recall@1 and recall@3 are the informative numbers.
A finding for Sprint 4: the best similarity score for the answerable questions was between 0.64 and 0.84 and for the three unanswerable questions between 0.71 and 0.78. The ranges overlap, and the lowest answerable score (0.64, Q5) is below all three unanswerable ones. On this data no score cutoff separates "answerable" from "unanswerable", so the not-found decision cannot be left to retrieval and must come from the model being told to say "not found in the document" and from citation checks. The cutoff stays disabled.
The SQL ranking was compared with the script's in-memory dot-product ranking for all ten questions with the real model: identical order for 10 of 10. `EXPLAIN (ANALYZE, BUFFERS)` on a table of 9,758 chunks over 40 documents: Bitmap Index Scan on `document_chunks_doc_index_uidx` (`Index Cond: document_id = ...`), a Bitmap Heap Scan with `Filter: owner_id = ...`, a quicksort of 8 rows in 28 kB, `Buffers: shared hit=32`, execution time 0.088 ms. The filter on `document_id` narrows the table to one document's rows before any distance is computed, which is why no vector index is needed (ADR-009).
Consequences: the eval script is tiny and absorbed into the Sprint 4 runner. The eval covers one document, so claims about retrieval quality stay modest until S4-1 adds documents. The retrieval eval, the chunker (ADR-033) and the embedder (ADR-034) now form a measured baseline: any change to one of them is compared against these numbers. The script's `evals/` folder is linted, type-checked and its pure helpers tested like the app, in `make check` and CI.
Alternatives: filtering by `document_id` only (relies on every caller's check), hybrid or full-text search (a stretch option in `docs/ai-engineering.md`, only if evals show retrieval is the bottleneck, which they do not here), an approximate vector index (no speed gain at this size, ADR-009), a score cutoff chosen now (the data above shows it would not work).

## ADR-038: The Anthropic SDK, the model, and two rules that no longer hold (2026-11-01)

Context: S2-7 is the first story that calls a language model. The rules in `AGENTS.md` and `docs/ai-engineering.md` were written before the current model documentation was read, and two of them do not work with the model named in `.env.example`.
Decision:
- Add the `anthropic` SDK (already in the fixed stack). The lock file now also holds its own dependencies (`httpx2`, `httpcore2`, `jiter`, and a few small ones). The model name is the setting `ANTHROPIC_MODEL`, default `claude-sonnet-5-5`. The API key is the optional setting `ANTHROPIC_API_KEY`: the app and the tests start without it, and a chat request without one answers `503 llm_unavailable`. The key is a `SecretStr`, is never logged, and an empty value counts as missing.
- No `temperature`. The rule "temperature 0" cannot be followed: this model rejects any non-default `temperature`, `top_p` or `top_k` with a 400, and from 2026-10-21 the API rejects them on every model. `AGENTS.md` now says the code sends no sampling parameters, and a unit test checks that the request contains none. Repeatability comes from schema-constrained output, a fixed prompt version, low effort, and generation evals run three times, which `docs/ai-engineering.md` already required. A run can still vary; the evals measure how much.
- No forced tool call. The plan in `docs/ai-engineering.md` was to force the model to call a tool to get structured output. This model rejects a forced `tool_choice` with a 400. Structured outputs do the job: the request asks for a reply matching a JSON schema (`output_config.format`, the schema generated from the Pydantic model by the SDK's `transform_schema`), and the code validates the reply with the same Pydantic model. I call `messages.create` and validate myself, not `messages.parse`, because `parse` raises on a bad reply and loses the token counts, and a failed attempt still costs money and must be recorded. S3-3 (gap report) reuses the same client and call helper; `docs/sprints.md` wording for S3-3 was changed to match.
- Effort is `low`. This model thinks by default and its default effort is high. Answering a question from a few given sources needs little reasoning, and low effort keeps latency and cost down. It is a constant in `app/ai/client.py`, so changing it is a code change that comes with an eval run.
- Timeout and retries: an explicit timeout (`LLM_TIMEOUT_SECONDS`, 60) and the SDK's own retries limited to two, which cover 429, 5xx, connection errors and timeouts with backoff, as `docs/ai-engineering.md` specifies. Every SDK error becomes one of three domain errors, all `503`: `llm_unavailable`, `llm_timeout`, `llm_invalid_output`. Only the status code of a provider error is logged, because its body can echo the request.
Consequences: a real call to the API has not been run in this environment, because there is no key here. Everything about the real model's behaviour (answer quality, latency, cost per question, whether low effort is enough) is unmeasured until the owner sets a key and Sprint 4 builds the generation evals. The tests use a fake client that is given the same inputs and records them.
Alternatives: temperature 0 on an older model (the sampling parameters are going away on all models), forcing a tool call (rejected by the model), `messages.parse` (loses token counts on invalid output), a hand-written HTTP client (more code to own, no retry or timeout handling), prompt caching (the sources change with every question, so there is almost nothing stable to cache).

## ADR-039: How a chat answer is made and checked (2026-11-01)

Context: chat is the second place where model output reaches a user. The rule is the one in `docs/ai-engineering.md`: the model proposes, the code verifies.
Decision:
- Order of work in `answer_question`: retrieve the best chunks (S2-6, which also checks the document is the user's, live and ready), load the thread and its last four messages if a thread id was given, build the prompt, call the model, verify, then write everything in one transaction. A new thread is created only after a successful answer, so a failed call leaves no empty thread.
- The prompt is one fixed system prompt (`app/ai/prompts/chat_answer.v1.md`, version recorded with every call) and one user turn built by a single function. The sources, the history and the question all go in the user turn inside tags the system prompt declares to be data, and `<` and `>` in all of them are escaped, so none can close a tag. No user or document text is ever in the system prompt; a test sends `</source>` and `<system>` through every field. The v1 text is a draft written from the contract in `docs/ai-engineering.md` and is for the owner to review, since prompts are theirs to own.
- Verification in `app/modules/chat/grounding.py`, a pure function: a cited number must be a real source (numbers outside the sources the model was shown, zero, negatives and repeats are dropped); the quote and the section label come from the stored chunk and never from the model; a reply that is not grounded, has no valid citation, or has an empty answer becomes the fixed text "This is not found in the document." with no citations. The model's own wording is only shown when a valid citation backs it. This is stricter than the minimum in the doc, on purpose: a refusal written in the model's words, or a guess that cites nothing, never reaches the user.
- The quote is the first 300 characters of the cited chunk, cut at a word boundary. It is verbatim by construction (a prefix of stored text), and it is a display aid, not proof of which sentence supports the answer. Pointing at the exact sentence is left for the report UI (S3-6).
- `llm_calls` gets one row per attempt, with sizes and outcome only, and no prompt or answer (a test dumps the table and looks for the question and the document text). The rows of a failed call are committed before the error is raised, because raising rolls the transaction back. A reply that does not match the schema gets one repair attempt that includes the validation problem (field paths and messages only, never the rejected text); a refusal or a cut-off reply is not retried because a repeat would not help.
- A question and its answer are written in one transaction with explicit timestamps one microsecond apart. `now()` is the same for every row of a transaction, and without this the order of the pair would be undefined.
- Messages are read with keyset pagination on `(created_at, id)`, with an opaque cursor in `app/core/pagination.py` that the documents list can reuse. Measured with `EXPLAIN (ANALYZE, BUFFERS)` on 10,000 messages in 200 threads: fetching the last four messages is an index scan backward on `chat_messages_thread_created_idx`, 0.033 ms; a page of 21 is an index scan on the same index, 0.053 ms. The thread lookup showed a sequential scan only because the test table had 200 rows; the primary key index exists for real sizes.
- 30 questions per hour per user, keyed by the user id from the token (`docs/security.md`).
Consequences: the answer text stored in the conversation is the verified one, so reading it back never shows something that was not shown at the time. Follow-up questions are retrieved from the current question only (query rewriting is a stretch option). Nothing here limits spend per day; that is S3-7, which will read `llm_calls`. The threads list endpoint is not built and no story owns it.
Alternatives: showing the model's own "not found" wording (varies, can contain a guess), a quote chosen by the model (it can invent text; it would need verifying against the chunk anyway), letting the model produce citations as chunk ids (it only ever sees the numbers), one transaction for the model call and the writes (a failure would erase the record of the cost).

## ADR-040: The three read endpoints the UI needs (2026-11-01)

Context: `docs/api.md` listed `GET /documents`, `GET /documents/{id}/chunks` and `GET /documents/{id}/threads`, but no sprint story built them. The documents table, the document pane and the restored conversation of S2-8b need them, so the owner chose to build all three first (S2-8a).
Decision:
- Lists use keyset pagination on the sort columns: documents by `(created_at, id)` descending, threads by `(updated_at, id)` descending, messages by `(created_at, id)` ascending. One extra row is fetched to learn whether another page exists, and `core/pagination.py` (`split_page`) turns the rows into a page and an opaque cursor. The message list from S2-7 was moved onto the same helper; its tests are unchanged and pass.
- The chunks endpoint is not paginated. The source pane needs the whole text, and `MAX_CHUNKS_PER_DOCUMENT` (1000) bounds the response, so this is a deliberate exception to the pagination convention in `docs/api.md`. The worst case is roughly 1000 chunks of at most 400 tokens each.
- Every query takes `owner_id`, and each one is also tested directly with a wrong owner and a right document id (the service checks ownership first, so without that test the filter in the query could be deleted unnoticed; a mutation check showed exactly that). A missing, foreign and deleted document give the same 404 on all three.
- `DocumentNotReady` moved from the retrieval module to the documents module, because the documents service now raises it too and retrieval already depends on documents, not the other way round.
- The thread list is a read of the chat module and checks the document through the documents service first (modules call each other's services, not repositories).
Measured with `EXPLAIN (ANALYZE, BUFFERS)` on 10,000 documents of 20 owners, one document with 300 chunks and 200 threads: the first page and a later page of the documents list are index scans on `documents_owner_created_idx` (0.031 ms and 0.054 ms); the thread list is an index scan on `chat_threads_document_updated_idx` with an incremental sort (0.038 ms). The chunks query showed a sequential scan (0.242 ms) only because every row in that test table belongs to the one document, so reading all of it is the cheapest plan; with chunks of many documents in the table it uses `document_chunks_doc_index_uidx`, as the retrieval query did in ADR-037.
Consequences: no migration and no dependency. The list reads only the six columns a table shows. A client that wants a full document text makes one request of up to a few hundred kilobytes.
Alternatives: paginating chunks (the pane would need to stitch pages and scroll-load before a citation can highlight a section), offset pagination (slow and unstable while documents are being added, and ruled out by `docs/database.md`), returning the full document object in the list (more data than a table shows).

## ADR-041: How the documents and chat screens are built (2026-11-01)

Context: S2-8b adds the first screens that do real work: the documents table, the upload dialog, and the workspace with the document text and the chat. The rules are in `docs/design-system.md`; these are the choices it leaves open.
Decision:
- An upload is one multipart `fetch` through `apiRequest`, the only place that calls `fetch`. A `FormData` body is sent as it is and no `Content-Type` is set by hand, because the browser has to write the multipart boundary itself. A test checks the header is absent. The dialog shows an "Uploading" state, not a percentage, because `fetch` cannot report upload progress; `XMLHttpRequest` could, but would be a second way to call the server and would bypass the token refresh in `apiRequest`.
- A file over 5 MB is refused in the browser without a request. The server still checks everything (size, type by content, pages, text, duplicates); the browser check only saves sending 5 MB to be told no. Server refusals are turned into fixed sentences by error code. The text the server sends is never shown.
- Status polling is `refetchInterval` on the list and on the single-document query, 2 seconds as `docs/api.md` says, and only while something is `uploaded` or `processing`. The list refetches every page loaded so far, which is at most a few requests of 20 rows each. A test with fake timers checks it polls and then stops.
- Status is words plus an icon (Queued, Processing, Ready, Failed), never color alone. The one new color token is `success` (`#17663a`), computed at 7.0:1 on the surface and at least 6.18:1 on every background, recorded in the design system. Failed rows in the table show only the badge, because the list endpoint does not carry `error_message`; the message is shown in the workspace.
- The workspace keeps both panes in the page. From 1024 px up they sit side by side; below, tabs show one at a time (`forceMount` plus a `!` important utility so the large-screen layout wins over the hidden attribute). Choosing a source in the chat switches to the Document tab on a narrow screen so the marked section is visible. The marked section has `aria-current`, so the mark is not only a color.
- The chat restores the latest thread by asking for the first thread of the document (`limit=1`), then reads all messages of it by following the cursor (pages of 100). Sending a question shows the question and "Answering" at once, and the answer appears together with the stored messages: the mutation waits for the message list to be read again instead of editing the cache by hand, so what is shown is always what the server stored. A thread that has vanished starts a new one on the next try.
- Text from the model, the server and the document is rendered as text. ESLint already forbids `dangerouslySetInnerHTML`; a test also renders `<img onerror>`, `<b>` and `<script>` strings and checks no element is created.
- No toasts. Sonner would be a new dependency, and every confirmation here is visible in the table (the new row, the vanished row).
- The shadcn components came from the CLI. They imported `cn` from an npm package of that name instead of `@/lib/utils`, which I corrected, and I removed the shadows and the 3 px focus ring that the design system does not allow. The CLI did not change `package.json` or the lock file.
- Test infrastructure: a request that a test did not plan for now fails the test even if the app catches the error and shows an error screen (it used to be possible for a screen to quietly call an endpoint no test mentioned; eleven existing tests were doing that for the documents list and got a stub). jsdom has no `ResizeObserver`, which Radix menus need, so setup defines a no-op one.
Consequences:
- Nothing was looked at in a browser here. Layout, spacing, the narrow-screen tabs, focus rings and the dialog placement are verified only through Testing Library tests and a successful production build. The owner should look at the screens once against `docs/design-system.md`.
- The package `cn` (version 0.5.1) is listed in `frontend/package.json` but nothing imports it any more. It looks left over from the first shadcn run. Removing it is a dependency change, so I left it for the owner.
- Real chat answers were not seen (ADR-038).
Alternatives: `XMLHttpRequest` for upload progress, optimistic edits of the query cache for new messages (can show an answer the server did not store), a separate full-width page layout for the workspace (the route `handle` keeps one layout), server-sent updates instead of polling (the API has none, and polling is what `docs/api.md` specifies).

## ADR-042: The analysis tables (2026-11-02)

Context: S3-1 adds `analyses`, `findings` and `finding_citations`, the tables the gap report (S3-2 to S3-6) writes and reads. No endpoint or service uses them yet. The DDL was already fixed in `docs/database.md`; these are the choices around it that the owner must be able to explain.
Decision:
- The migration (`0004`) and the models (`app/modules/analysis/models.py`) follow `docs/database.md` exactly, and the existing `compare_metadata` test proves they agree. A mutation check (a changed nullability and a dropped `unique` on the findings index) made that test fail.
- At most one active analysis per document is enforced by a partial unique index on `document_id` where `status IN ('queued', 'running')`. The start endpoint (S3-5) will insert and turn the index's violation into `409`, the same way duplicate emails and duplicate uploads work (ADR-018, ADR-031). A "look for a running one, then insert" sequence has a race: two clicks or two tabs could both pass the look and both spend model budget. Tests cover the four ways a second active row can arrive, and that finished analyses (any number), other documents, and a just-finished analysis do not block a new one. A mutation check that removed the `WHERE` clause failed the tests for exactly those cases.
- `analyses` has no `updated_at`, which departs from the `AGENTS.md` wording "where rows change" and follows `docs/database.md`. The status moves forward a few times within minutes. The stuck-job sweep for analyses (`docs/architecture.md`) will use `created_at`: an analysis still `queued` or `running` more than 15 minutes after it was created is stuck, because a run is bounded by the call timeout and two retries. `findings` has `updated_at` because the review status is edited by the user later. `finding_citations` has no `created_at`; a citation is written once with its finding.
- Only `analyses` carries `owner_id`. Findings and citations are reached through the analysis, so every repository method that returns findings must join `analyses` and filter on its `owner_id` (S3-5), including `PATCH /findings/{id}`. A finding id on its own is never enough to read or change a row.
- Citations are rows, not a `jsonb` snapshot as in chat, because they are verified against a chunk, joined to the report, and must disappear when the chunk does. `chunk_id` is `ON DELETE CASCADE`, so deleting a document's chunks (ADR-036) removes the quotes that were copied from them.
- Each new index has a stated query: latest analysis of a document (`analyses_document_created_idx`), report order (`findings_analysis_position_uidx`), the findings-to-citations join (`finding_citations_finding_id_idx`), and the cascade when chunks are deleted (`finding_citations_chunk_id_idx`). Without the last one, each deleted chunk would scan the whole citations table. No `EXPLAIN` is recorded because no query uses these tables yet; S3-5 ships the first ones with their plans.
- Status, kind, severity and review status are text with `CHECK` constraints, not Postgres enums (`docs/database.md`). `llm_calls.purpose` already allows `gap_report`, so that table is unchanged.
Consequences:
- Open item for S3-5: the soft delete of a document (ADR-036) removes the chunks and, through the cascade, the citation quotes. It does not remove `findings.title`, `findings.description`, `findings.suggested_question` or `analyses.summary`, which are text derived from the document and would stay for the 30-day retention. The owner chose to fix this in S3-5, where analysis rows are first created: the delete transaction will also remove the document's analyses (findings and citations cascade), and a test will prove it. A test already documents the current behavior (a finding survives the deletion of its chunk). The analysis's finishing step must also be guarded against a deleted document, as the document processing task is (ADR-036).
- Downgrade deletes every analysis, finding and citation, and says so in a comment.
- A finding can cite a chunk of another user's document in the database; nothing in the schema forbids it. The code that stores citations (S3-4, S3-5) only ever uses chunks of the analysed document, which the verifier receives from that document's own chunk list.
Alternatives: an `updated_at` on `analyses` (the owner chose to follow the DDL; the sweep does not need it), `owner_id` on findings and citations (fewer joins, but two more redundant columns that nothing forces to match), a check-then-insert for the single active analysis (race), a `jsonb` column of findings on `analyses` (cannot be joined, filtered by review status or checked by foreign keys).

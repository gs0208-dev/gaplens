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

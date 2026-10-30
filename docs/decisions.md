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

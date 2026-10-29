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

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

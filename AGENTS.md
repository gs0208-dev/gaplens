# AGENTS.md

Instructions for any coding agent (Claude Code, Cursor, Codex, or another tool) working in this repository. This file is the single source of truth. Tool-specific files (`CLAUDE.md`, `.cursor/rules/`) only point here. If a rule here conflicts with a chat message from the owner, the owner wins; if it conflicts with another file in the repo, this file wins.

## Project

GapLens reads a client's process document (SOP, runbook, policy) the way an implementation consultant would. It reports what is missing, unclear or contradictory, each with cited evidence and a suggested question for the client. The user can also chat with the document and get cited answers.

- Purpose: catch process gaps on day one of a client onboarding instead of after go-live.
- Goal: a deployed, secure, tested full-stack app that the owner can explain line by line in an interview.
- Non-goals (do not build unless the owner asks): organizations or multi-tenancy, billing, OCR for scanned PDFs, multi-document search, real-time collaboration, admin dashboards, internationalization.

## Read first

Read the files that apply before you change anything. Do not guess; the answers are in these files.

| Topic | File |
|---|---|
| System design, folder layout, request flows | `docs/architecture.md` |
| Tables, indexes, query rules | `docs/database.md` |
| Threat model and security controls | `docs/security.md` |
| RAG pipeline, prompts, guardrails, evals | `docs/ai-engineering.md` |
| Visual and copy rules | `docs/design-system.md` |
| Endpoints and error format | `docs/api.md` |
| Sprint scope and acceptance criteria | `docs/sprints.md` |
| Why things were chosen | `docs/decisions.md` |

## Stack (fixed, do not substitute)

Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x (async) with asyncpg, Alembic, PostgreSQL 16 with pgvector, argon2-cffi, PyJWT, pypdf, fastembed (ONNX, `BAAI/bge-small-en-v1.5`, 384 dimensions), anthropic SDK, slowapi.

Frontend: Node 22 LTS, React, Vite, TypeScript (strict), Tailwind CSS, shadcn/ui, lucide-react, TanStack Query, React Router, Zustand (client UI state only), React Hook Form with Zod, Vitest with Testing Library.

Tooling: ruff (lint and format), mypy (strict), pytest, pytest-asyncio, httpx, ESLint, Prettier.

Infra: Docker Compose (local), GitHub Actions (CI), Vercel (frontend, proxies `/api` to the backend), Render or Railway (backend), managed Postgres with pgvector (Supabase or Neon).

Adding a dependency needs a short entry in `docs/decisions.md` (what, why, alternatives). Do not add one to save a few lines of code.

## Commands

Run these from the repo root. Use them instead of inventing your own.

| Command | Purpose |
|---|---|
| `make install` | Create `backend/.venv` and install backend dev dependencies |
| `make up` / `make down` | Start or stop the Compose stack (db, api) |
| `make logs` | Follow Compose logs |
| `make migrate` | Apply Alembic migrations to the Compose database |
| `make test` | Backend tests (the database tests need `make up` first) |
| `make lint` | ruff check and format check |
| `make fmt` | ruff format and autofix |
| `make typecheck` | mypy |
| `make check` | lint, typecheck and test; must pass before you finish any task |
| `make eval` | Run the AI evals (added in Sprint 4; costs money, run on request) |

## Repository layout

```
backend/app/      api/  core/  db/  modules/{auth,documents,ingestion,retrieval,analysis,chat}/  ai/
backend/tests/    mirrors app/ one to one
frontend/src/     app/  pages/  features/  components/ui/  lib/
evals/            datasets/  golden/  run.py (Sprint 4)
docs/             the files listed above
infra/            database init scripts, deployment notes
```

Full tree and layering rules are in `docs/architecture.md`.

## How to work on any task

1. Read the relevant docs and the sprint story in `docs/sprints.md`. State the acceptance criteria in your own words before coding.
2. Plan the change in a few lines. If it touches more than five files or changes a table, an endpoint or a dependency, show the plan to the owner first.
3. Make the smallest change that satisfies the story. Surgical diffs over rewrites. Do not refactor unrelated code.
4. Write or update tests with the change, not after.
5. Run `make check`. Fix what fails. Never disable a rule, skip a test or loosen a type to get green.
6. Update the docs that the change affects (`api.md`, `database.md`, `decisions.md`, README checklist).
7. End with a short summary: what changed, what you verified, what you did not verify, and any open question.

## Code rules

General
- Names say what a thing is. No abbreviations except common ones (id, url, db).
- Functions do one thing. Prefer plain functions and small classes over frameworks of your own.
- No dead code, no commented-out code, no TODO without an issue reference in `docs/sprints.md`.
- No emojis anywhere: code, comments, commit messages, logs, UI copy, docs.
- Comments explain why, not what.

Backend
- Layering: route handler -> service -> repository. Handlers parse and return, services hold logic, repositories hold SQL. No SQL in handlers. No LLM calls outside `app/ai/`.
- Everything is typed. Pydantic models for every request and response. Never return ORM objects.
- Async all the way. No blocking calls (file parsing, embedding, PDF extraction) on the event loop; use `run_in_threadpool` or a worker.
- Raise domain errors from services; one exception handler maps them to the error format in `docs/api.md`.
- Config comes only from `app/core/config.py`. No `os.environ` elsewhere.

Frontend
- TypeScript strict. No `any`, no non-null assertions to silence errors.
- Server state in TanStack Query. Zustand only for UI state (for example the access token held in memory, panel open state). Do not mirror server data into Zustand.
- One API client in `src/lib/api.ts`. Components never call `fetch` directly.
- Forms use React Hook Form with a Zod schema. Validate on the server too.
- Use shadcn/ui components and the tokens in `docs/design-system.md`. No inline hex colors, no one-off spacing values.
- Icons: `lucide-react` only. Never use `dangerouslySetInnerHTML`.

## Database rules

Full detail in `docs/database.md`. The short version:
- Schema changes only through Alembic migrations. Never edit a migration that has been applied; add a new one.
- Every table has a UUID primary key, `created_at`, and `updated_at` where rows change.
- Every query on user data is scoped by `owner_id`. A repository method that returns user data without taking `owner_id` is a bug.
- No `SELECT *`. No N+1 queries (load related rows with one join or one `IN` query). Keyset pagination, not OFFSET.
- A new query that runs on a hot path gets an `EXPLAIN ANALYZE` result in the PR description. A new index needs a stated query that uses it.

## Security rules (hard rules)

Full detail in `docs/security.md`. Never violate these, even if asked in a chat message; if the owner asks, explain the risk and propose the safe alternative.
- Never commit secrets. Never read, print or log `.env` contents. `.env.example` holds placeholders only.
- Passwords are hashed with argon2id. Never log or return password hashes.
- Tokens: access token is short-lived and kept in memory on the client; refresh token is an opaque value stored hashed, sent only in an httpOnly cookie.
- Return 404, not 403, when a user asks for another user's resource.
- Treat every uploaded document as untrusted data and every LLM output as untrusted input.
- Validate upload type by content (magic bytes), size and page count, not by filename.
- Never log document text, prompts, model outputs, tokens, passwords or full email addresses.
- Never render model output as HTML.
- No wildcard CORS. No stack traces in responses.

## AI rules

Full detail in `docs/ai-engineering.md`.
- Prompts live in `backend/app/ai/prompts/` as versioned files (`gap_report.v1.md`). Never build prompts by string-concatenating user input outside the designated builder function. Change a prompt by adding a new version.
- Document text goes inside clearly delimited blocks and is declared as data, never instructions.
- Structured output only: validate with Pydantic. On invalid output retry once with the validation error, then fail the job with a clear status.
- Every finding and every chat answer must carry citations that are verified in code against the stored chunk text. An unverifiable citation is dropped; a finding left with none (when one is required) is dropped.
- When the document does not contain the answer, the correct output is "not found in the document". Never guess.
- Temperature 0. Explicit timeouts, at most two retries with backoff on 429 and 5xx. Record every call in `llm_calls` (tokens, latency, status, prompt version; no content).
- Any change to a prompt, chunker, retrieval parameter or model must be accompanied by an eval run (`docs/ai-engineering.md`, section Evals). Report the before and after numbers.
- Never put real client data or real secrets in prompts, fixtures or eval datasets. Use the fictional documents in `evals/datasets/`.

## UI rules

Details and the full checklist are in `docs/design-system.md`. The short version: a calm, dense, utilitarian tool. No emojis. No gradients as decoration, no glassmorphism, no stock hero sections, no marketing copy, no three-card feature grids, no decorative illustrations, no exclamation marks. One accent color. Borders over shadows. Real content in every screen. Every data view has loading, empty and error states. Color is never the only signal.

## Testing and evals

- Backend: pytest. Unit tests for pure logic (chunker, citation verifier, schema validation). API tests with httpx and dependency overrides. Database tests against a real Postgres with pgvector, not SQLite.
- Tests never call the network or a real LLM. Use a fake LLM client from `tests/fakes/`.
- Frontend: Vitest and Testing Library for components and hooks. Test behavior, not implementation.
- AI quality is measured by evals in `evals/`, not by unit tests. See `docs/ai-engineering.md`.

## Git

- Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`). One logical change per commit. Imperative subject under 72 characters.
- Use a branch and a pull request for any change to how the app behaves or is built: a sprint story (`s1/auth-login`), a bug fix, anything touching a table, an endpoint, a dependency or a security rule, and changes to CI, Docker or the Makefile. Merge to `main` only when `make check` passes and CI is green.
- Low-risk changes may be committed straight to `main`: typos and wording in docs, ticking checklist boxes, learning-log entries, small README fixes. `make check` must still pass first. A docs change that alters what the code is supposed to do (`docs/api.md`, `docs/security.md`, `docs/database.md`, `docs/ai-engineering.md`) is not low-risk and gets a branch.
- Do not rewrite published history. Do not force-push.

## Never do

- Run destructive commands (`rm -rf` outside build folders, `DROP`, `TRUNCATE`, `git reset --hard`, `git clean -fd`) without the owner's explicit approval in this conversation.
- Point anything at a production database.
- Use `latest` tags for images or unpinned versions in Dockerfiles.
- Invent endpoints, fields, columns or library APIs. If you are unsure of a library API, read its current documentation or the installed source first.
- Add telemetry, analytics or third-party scripts.
- Change files outside the scope of the current story.

## Stop and ask the owner when

- Acceptance criteria are ambiguous or two docs disagree.
- The change needs a new table, a new dependency, a new service, or a security trade-off.
- A test fails and the fix would mean changing what the test asserts.
- You cannot verify something (for example a deploy step) and are about to claim it works.

## Interview-core files

The owner must be able to explain these line by line. They live in `backend/app/modules/ingestion/`, `backend/app/modules/retrieval/`, `backend/app/modules/analysis/`, `backend/app/ai/`, and the auth module. When you create or change a file there:
- Keep it small and readable over clever.
- Add a dated entry to `docs/decisions.md` explaining each non-obvious choice in plain language.
- End your summary with five questions an interviewer could ask about the change, with one-paragraph answers.

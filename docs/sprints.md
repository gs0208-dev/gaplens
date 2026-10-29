# Sprints

Agile plan for one developer working with AI coding agents. Five sprints of about two days each. Every sprint ends with something demoable. Scope is the list of stories below; anything else goes to the parking lot.

## Working agreement

- Board: GitHub Projects with columns Backlog, Sprint, Doing, Done. One card per story. At most two cards in Doing.
- Daily (5 minutes, written on the card or in `docs/learning-log.md`): done yesterday, doing today, blocked.
- Story format: "As a (user), I can (action) so that (outcome)." Each story has acceptance criteria written as checkable statements.
- Branch per story (`s1/auth-login`), merge to `main` when `make check` passes and the acceptance criteria are verified.
- Sprint review: demo the sprint goal end to end, on a fresh clone if possible.
- Sprint retro: one line each for keep, stop, change, appended to `docs/learning-log.md`.
- Explain-back (15 minutes, every sprint): ask the agent to quiz you on the sprint's interview-core code (see `AGENTS.md`). Write your three-line summary in the learning log. A sprint is not done until you can answer without looking.

## Definition of done (every story)

1. Acceptance criteria met and demonstrated.
2. Tests written; `make check` passes.
3. Security checklist for the sprint (in `docs/security.md`) applied to the new code.
4. Docs updated (`api.md`, `database.md`, `decisions.md`, README checklist).
5. No secrets, no emojis, no dead code, no unrelated changes.
6. For AI changes: eval run recorded before and after.

## Sprint 0: Foundation

Goal: a clean repo that runs, with rules, CI and a health check.

| Story | Acceptance criteria |
|---|---|
| S0-1 Repository and agent rules | `AGENTS.md`, `CLAUDE.md`, Cursor rule, docs present; first commit contains the README |
| S0-2 Compose stack | `make up` starts Postgres with pgvector and the API; the pgvector extension exists |
| S0-3 Health endpoints | `/health/live` returns 200; `/health/ready` returns 200 when the database is reachable and 503 when not; both covered by tests |
| S0-4 Config, logging, request id | Settings from environment; every response carries `X-Request-ID`; logs include it |
| S0-5 CI | Lint, format check, typecheck and tests run on every push and pull request |

Verification checklist (to be done on the owner's machine):
- [x] `cp .env.example .env`, set `POSTGRES_PASSWORD`
- [x] `make up` succeeds, `make ps` shows `db` and `api` healthy
- [x] `curl localhost:8000/health/ready` returns `{"status":"ok","database":"up"}`
- [x] `docker compose exec db psql -U gaplens -c "\dx"` lists `vector`
- [x] `make install && make check` passes
- [x] Push to GitHub; CI is green

Explain-back: how `/health/ready` differs from `/health/live` and why a platform needs both; what the request id is for.

## Sprint 1: Access

Goal: a user can register, sign in, stay signed in across reloads, and sign out, with the security tests passing. Frontend scaffold and login screens included.

| Story | Acceptance criteria |
|---|---|
| S1-1 Migrations and user tables | Alembic configured; migration creates `users`, `refresh_tokens`, `audit_events`; applies from an empty database in CI |
| S1-2 Register | Valid registration returns 201; duplicate email returns 409; password length rules enforced; hash is argon2id |
| S1-3 Login and tokens | Correct credentials return an access token and set the refresh cookie with the required attributes; wrong password and unknown email give the same response; login is rate limited |
| S1-4 Refresh rotation | Refresh issues a new pair and revokes the old token; reuse of a revoked token revokes the family; `Origin` check enforced |
| S1-5 Current user and logout | `/auth/me` works with a valid token and fails otherwise; logout revokes and clears the cookie |
| S1-6 Ownership helper and audit | A reusable current-user dependency; audit events written for register, login, failed login, logout |
| S1-7 Frontend scaffold and auth screens | Vite, TypeScript strict, Tailwind and shadcn set up; sign in and register screens follow `docs/design-system.md`; access token held in memory; session restored through refresh on reload; `/api` proxy configured |
| S1-8 Dependency locks and secret scanning | Lock files committed and used in CI; gitleaks in CI and pre-commit |

Security tests: token tests 2, refresh rotation 3, login 4, rate limit 5, log test 7 from `docs/security.md`.

Explain-back: why the refresh token is hashed in the database, what token rotation protects against, why the access token is not stored in `localStorage`, how argon2id differs from SHA-256 for passwords.

## Sprint 2: RAG core

Goal: upload a document, see it processed, ask questions and get cited answers (API and a minimal UI).

| Story | Acceptance criteria |
|---|---|
| S2-1 Document tables | Migration for `documents` and `document_chunks`; indexes as in `docs/database.md` |
| S2-2 Upload validation | Size, magic-byte type, page and text caps, encrypted PDF and duplicate rejected; ownership enforced |
| S2-3 Extraction and structure detection | PDF, text and Markdown produce text with page numbers and detected section labels; unit tests on fixtures, including the sample SOP |
| S2-4 Chunker | Rules from `docs/ai-engineering.md` implemented; tests for clause chunks, merging of short clauses, splitting of long ones, unstructured fallback |
| S2-5 Embedding and storage | Chunks embedded in batches off the event loop and stored with one bulk insert; document reaches `ready`; failures end in `failed` with a safe message; stuck documents are swept |
| S2-6 Retrieval | Scoped query returns top-k with scores; test proves another user's document returns nothing |
| S2-7 Chat endpoint | Grounded answers with verified citations; not-found path works; fake LLM used in tests; `llm_calls` row written |
| S2-8 Documents and chat UI (minimal) | Upload dialog, documents table with status polling, document workspace with chat tab |

Evals: retrieval recall@k on `evals/golden/qa.jsonl` recorded.

Explain-back: what an embedding is, why chunk boundaries follow clauses, what cosine distance means, why the query includes `owner_id` even though `document_id` is unique, why the vector index is not needed yet.

## Sprint 3: Gap report and UI

Goal: the core feature. Generate a cited gap report and review it in the workspace.

| Story | Acceptance criteria |
|---|---|
| S3-1 Analysis tables | Migration for `analyses`, `findings`, `finding_citations`; one-active-analysis index |
| S3-2 Gap report prompt v1 | `gap_report.v1.md` written by the owner against the contract; prompt builder escapes the document; version recorded |
| S3-3 Structured call and validation | Forced tool call returns `GapReportOut`; invalid output gets one repair retry then `failed`; timeouts and retries as specified |
| S3-4 Citation verification | Quotes verified against chunks; evidence rules per kind enforced; dropped items counted; unit tests for exact, whitespace-different and fabricated quotes |
| S3-5 Analysis endpoints | Start (202), latest, by id, review status patch; 409 when already running; ownership tests |
| S3-6 Report UI | Summary, severity counts, filters, findings with evidence, copy suggested question, status control; evidence click highlights the source |
| S3-7 Token budget and limits | Per-user daily token budget and endpoint limits enforced from `llm_calls` |

Evals: gap recall and extra findings on the sample SOP; injection sample passes.

Explain-back: why the report does not use retrieval, how forced tool use gives structured output and why you still validate, how a fabricated quote is caught, what prompt injection is and which of your controls stops it.

## Sprint 4: Harden, evaluate, ship

Goal: a deployed, measured, defensible app.

| Story | Acceptance criteria |
|---|---|
| S4-1 Eval harness | `make eval` runs retrieval and generation evals three times, writes results and a comparison; at least two extra documents with golden files |
| S4-2 Calibration | `RETRIEVAL_MIN_SCORE` chosen from eval data; targets in `docs/ai-engineering.md` reviewed; results table in README |
| S4-3 Security pass | Headers and CSP, CORS review, dependency audit blocking, parsing isolation decision, account deletion, every item in the Sprint 4 checklist |
| S4-4 Reliability | Retries, stuck-job sweep, structured error pages in the UI, graceful behavior when the LLM is down |
| S4-5 Accessibility and design review | Keyboard and screen reader pass, contrast check, light and dark themes, checklist in `docs/design-system.md` |
| S4-6 Deploy | Backend on Render or Railway, database on Supabase or Neon, frontend on Vercel with the `/api` rewrite; environment variables set; migrations run; smoke test on the live URL |
| S4-7 Demo assets | README with screenshots or a short GIF, architecture diagram, evaluation results, limitations; a two-minute demo script |

Explain-back: the full request path from browser to database and back, what the evals measure and what they miss, what you would change first with another week.

## Parking lot (not in scope)

Interview coach mode, multiple documents per report, comparison of two versions of a document, export of the report to PDF or CSV, streaming chat answers, hybrid search and reranking, OCR, organizations and sharing, email notifications.

## Risks

| Risk | Mitigation |
|---|---|
| Time lost on UI polish | Use shadcn defaults and the tokens; polish only in S4-5 |
| LLM output varies between runs | Schema validation, citation verification, evals with three runs |
| Embedding model too heavy for the free host | Measure in Sprint 2; fall back to a hosted embedding API through the same interface if needed (new ADR) |
| Agent changes drift from the plan | `AGENTS.md`, small stories, `make check`, review every diff before merging |
| Owner cannot explain the code | Explain-back every sprint; interview-core files kept small |

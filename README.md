# GapLens

> Find the gaps in a client's process document before go-live.

## The problem

When a company onboards a client, the client hands over messy SOPs and email threads. Implementers read them manually and often miss gaps, like an undefined escalation owner or a missing refund limit. These get found late, after go-live, which causes rework and delays.

## The solution

GapLens reads a process document the way an implementer would. It reports what is missing, unclear or contradictory, with the exact section cited and a suggested question for the client. You can also chat with the document and get answers with sources. Questions go to the client on day one.

## Features

- [ ] Register and login (JWT, roles)
- [ ] Upload PDF or text documents
- [ ] Gap report: missing, unclear, contradictory, each with a citation
- [ ] Chat with the document (RAG, answers with sources)
- [ ] "Not found in the document" instead of guessing
- [ ] Per-user data isolation
- [ ] Evaluation suite with published results

## Tech stack

| Layer | Tools |
|---|---|
| Backend | Python, FastAPI, Pydantic, SQLAlchemy (async), Alembic |
| Database | PostgreSQL 16 with pgvector |
| AI | Claude API, fastembed (local embeddings) |
| Frontend | React, TypeScript, Tailwind, shadcn/ui, lucide-react |
| DevOps | Docker Compose, GitHub Actions, Vercel, Render |

## Architecture

See [docs/architecture.md](docs/architecture.md). Diagram of the ingestion and answer flows is in that file.

## Getting started

Requires Docker, Python 3.12, Node 22 and make.

```bash
cp .env.example .env        # then edit POSTGRES_PASSWORD
make up                     # starts Postgres (with pgvector) and the API
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

For backend development:

```bash
make install                # creates backend/.venv
make migrate                # applies database migrations to the Compose database
make check                  # lint, typecheck, tests (database tests need make up)
```

For frontend development (the backend must be running, and `JWT_SECRET` must be set in `.env`):

```bash
nvm use                     # in frontend/, picks Node 22 from .nvmrc
make frontend-install       # installs from package-lock.json
make frontend-dev           # http://localhost:5173, proxies /api to the backend
```

## Documentation

| File | Contents |
|---|---|
| [AGENTS.md](AGENTS.md) | Rules for any coding agent working in this repo |
| [docs/architecture.md](docs/architecture.md) | System design, folder layout, flows |
| [docs/database.md](docs/database.md) | Tables, indexes, query rules |
| [docs/security.md](docs/security.md) | Threat model and controls |
| [docs/ai-engineering.md](docs/ai-engineering.md) | RAG design, prompts, guardrails, evals |
| [docs/design-system.md](docs/design-system.md) | Visual and copy rules |
| [docs/api.md](docs/api.md) | Endpoints and error format |
| [docs/sprints.md](docs/sprints.md) | Agile plan with stories and acceptance criteria |
| [docs/decisions.md](docs/decisions.md) | Architecture decision records |

## Roadmap

- [x] Sprint 0: Foundation (repo, Docker Compose, health endpoints, CI)
- [ ] Sprint 1: Auth
- [ ] Sprint 2: RAG core
- [ ] Sprint 3: Gap report and UI
- [ ] Sprint 4: Security hardening, evaluation, deploy

## Evaluation

Results of the evaluation suite will be published here in Sprint 4.

## Limitations and future work

- One document at a time
- Text-based PDFs only (no OCR)
- No human review workflow beyond marking findings as confirmed or dismissed

## Author

Giridhar S

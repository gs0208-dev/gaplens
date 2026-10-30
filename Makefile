.PHONY: help install up down logs ps migrate test lint fmt typecheck check db-shell frontend-node frontend-install frontend-dev frontend-check

PYTHON ?= python3.12
VENV := backend/.venv
BIN  := $(VENV)/bin

help: ## List commands
	@grep -E "^[a-zA-Z_-]+:.*## " $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "%-12s %s\n", $$1, $$2}'

install: ## Create backend venv and install dev dependencies
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install --upgrade pip
	$(BIN)/python -m pip install -e "backend[dev]"

up: ## Start db and api with Docker Compose
	docker compose up --build -d

down: ## Stop the Compose stack
	docker compose down

logs: ## Follow Compose logs
	docker compose logs -f --tail=100

ps: ## Show Compose service status
	docker compose ps

migrate: ## Apply database migrations to the Compose database
	cd backend && .venv/bin/alembic upgrade head

test: ## Run backend tests (database tests need make up)
	cd backend && .venv/bin/pytest

lint: ## ruff check and format check
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .

fmt: ## ruff format and autofix
	cd backend && .venv/bin/ruff check --fix . && .venv/bin/ruff format .

typecheck: ## mypy
	cd backend && .venv/bin/mypy app

check: lint typecheck test frontend-check ## Lint, typecheck and test, backend and frontend (must pass before finishing a task)

# The frontend is built and tested on Node 22 (frontend/.nvmrc), the version CI uses.
frontend-node:
	@node -e 'process.exit(process.versions.node.split(".")[0] === "22" ? 0 : 1)' || \
		(echo "The frontend needs Node 22 and this shell has $$(node --version). Run: cd frontend && nvm use" && exit 1)

frontend-install: frontend-node ## Install frontend dependencies from the lock file (Node 22)
	cd frontend && npm ci

frontend-dev: frontend-node ## Start the frontend dev server on port 5173 (proxies /api to port 8000)
	cd frontend && npm run dev

frontend-check: frontend-node ## Frontend lint, format check, typecheck and tests
	cd frontend && npm run lint && npm run format:check && npm run typecheck && npm test

db-shell: ## Open psql in the db container
	docker compose exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

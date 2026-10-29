.PHONY: help install up down logs ps test lint fmt typecheck check db-shell

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

test: ## Run backend tests
	cd backend && .venv/bin/pytest

lint: ## ruff check and format check
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .

fmt: ## ruff format and autofix
	cd backend && .venv/bin/ruff check --fix . && .venv/bin/ruff format .

typecheck: ## mypy
	cd backend && .venv/bin/mypy app

check: lint typecheck test ## Lint, typecheck and test (must pass before finishing a task)

db-shell: ## Open psql in the db container
	docker compose exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

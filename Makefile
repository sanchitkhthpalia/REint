# Common tasks. Run `make help` for the list.
PY ?= python3
VENV := backend/.venv
VPY := $(VENV)/bin/python
FRONTEND := frontend

.DEFAULT_GOAL := help
.PHONY: help setup snapshot test lint dev up down

help: ## List targets
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

setup: ## Create the Python venv and install backend + frontend dependencies
	$(PY) -m venv $(VENV)
	$(VPY) -m pip install --upgrade pip
	$(VPY) -m pip install -e "backend[dev]"
	cd $(FRONTEND) && npm ci

snapshot: ## Re-download the Elexon data snapshot into data/
	$(VPY) scripts/build_snapshot.py

test: ## Run backend (pytest) and frontend (vitest) tests
	cd backend && .venv/bin/pytest -q
	cd $(FRONTEND) && npm test

lint: ## Lint and type-check backend (ruff) and frontend (eslint, tsc)
	$(VENV)/bin/ruff check backend scripts api --config backend/pyproject.toml
	$(VENV)/bin/ruff format --check backend scripts api --config backend/pyproject.toml
	cd $(FRONTEND) && npm run -s lint && npm run -s typecheck

dev: ## Run API (:8000, auto-reload) and Vite dev server (:5173) together
	@trap 'kill 0' INT TERM EXIT; \
	(cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000) & \
	(cd $(FRONTEND) && npm run dev) & \
	wait

up: ## Build and start the full stack in Docker on http://localhost:8080
	docker compose up --build -d
	@echo "App: http://localhost:8080   API docs: http://localhost:8080/api/docs"

down: ## Stop the Docker stack
	docker compose down

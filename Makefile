.PHONY: up down logs build test fmt seed migrate backend-shell

up:                ## Boot the full stack
	docker compose up --build

down:              ## Stop and remove containers
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

test:              ## Run backend tests
	docker compose run --rm backend pytest -q

fmt:               ## Format + lint backend
	docker compose run --rm backend ruff check --fix . && docker compose run --rm backend ruff format .

migrate:           ## Apply DB migrations (Phase 1+)
	docker compose run --rm backend alembic upgrade head

seed:              ## Seed templates + sample agents (Phase 10)
	docker compose run --rm backend python -m scripts.seed

backend-shell:
	docker compose run --rm backend bash

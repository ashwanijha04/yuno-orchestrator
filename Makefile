.PHONY: up down logs build test fmt seed migrate backend-shell bridge-logs

up:                ## Boot the full stack (auto-selects free host ports + claude bridge)
	./scripts/dev-up.sh --build

down:              ## Stop and remove containers (and the host claude bridge)
	-@[ -f .bridge.pid ] && kill "$$(cat .bridge.pid)" 2>/dev/null && echo "claude bridge stopped"; rm -f .bridge.pid
	docker compose down

bridge-logs:       ## Tail the host claude bridge log
	tail -f /tmp/yuno-claude-bridge.log

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

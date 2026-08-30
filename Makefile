.PHONY: install lint typecheck test cov run migrate seed compose-up compose-down docker-build

install:
	pip install -e ".[dev]"

lint:
	ruff check src tests
	ruff format --check src tests

typecheck:
	mypy

test:
	pytest -q

cov:
	coverage run -m pytest -q && coverage report -m

run:
	uvicorn flux.api.app:app --reload --host 0.0.0.0 --port 8000

migrate:
	alembic upgrade head

seed:
	python scripts/seed.py

compose-up:
	docker compose up --build -d

compose-down:
	docker compose down -v

docker-build:
	docker build -t flux-control-plane:local .

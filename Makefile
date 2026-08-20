.PHONY: help install dev test test-prop test-e2e bench lint format db-up db-down docker-build

help:
	@echo "ImpleGym Developer Commands:"
	@echo "  make install      Install package in editable mode with dev dependencies"
	@echo "  make dev          Start local development server"
	@echo "  make sync-yosupo  Clone/pull and sync all Yosupo problems into PostgreSQL"
	@echo "  make test         Run automated pytest test suite"
	@echo "  make test-prop    Run Hypothesis property-based tests"
	@echo "  make test-e2e     Run Playwright E2E browser tests"
	@echo "  make bench        Run performance benchmarks"
	@echo "  make lint         Run Ruff linter and Mypy type-checker"
	@echo "  make format       Run Ruff auto-formatter"
	@echo "  make db-up        Start PostgreSQL service via Docker Compose"
	@echo "  make db-down      Stop PostgreSQL service"
	@echo "  make docker-build Build multi-stage production Docker image"

install:
	pip install -e ".[dev]"

sync-yosupo:
	python -m implegym.cli sync-yosupo

dev:
	python -m implegym.cli serve --reload

test:
	pytest -v

test-prop:
	pytest tests/test_sampler_property.py -v

test-e2e:
	pytest tests/e2e/ -v

bench:
	pytest tests/benchmark/ -v

lint:
	ruff check .
	mypy implegym

format:
	ruff format .

db-up:
	docker compose up -d db

db-down:
	docker compose down

docker-build:
	docker compose build

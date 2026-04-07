clean:
	@docker compose down --remove-orphans --volumes
up_clean: clean
	@docker compose up --build -d
up:
	@docker compose up -d
down:
	@docker compose down --remove-orphans
ps:
	@docker compose ps
lint:
	ruff check producer consumer tests
	black --check producer consumer tests
	cd producer && mypy main.py observability.py
	cd consumer && mypy main.py document_id.py observability.py wikimedia_mappings.py
lint-docker:
	docker compose --profile test run --rm test-runner sh -ec "\
		ruff check producer consumer tests && \
		black --check producer consumer tests && \
		cd producer && mypy main.py observability.py && \
		cd ../consumer && mypy main.py document_id.py observability.py wikimedia_mappings.py"
test:
	@docker compose --profile test run --rm test-runner pytest tests/ -v
test-integration:
	@docker compose --profile test run --rm test-runner pytest tests/ -v --integration
test-build:
	@docker compose --profile test build test-runner
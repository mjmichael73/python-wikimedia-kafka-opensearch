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
test:
	@docker compose --profile test run --rm test-runner pytest tests/ -v
test-integration:
	@docker compose --profile test run --rm test-runner pytest tests/ -v --integration
test-build:
	@docker compose --profile test build test-runner
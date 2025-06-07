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
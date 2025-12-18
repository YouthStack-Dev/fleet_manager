# Makefile for Fleet Manager Database Migrations
# Usage: make <target>
# Example: make migrate-create MSG="add user email"

.PHONY: help migrate-init migrate-create migrate-upgrade migrate-downgrade migrate-current migrate-history migrate-test validate clean

# Default Python interpreter
PYTHON := python
PIP := pip

# Help target
help:
	@echo "Fleet Manager Migration Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  make migrate-init                 - Initialize database (upgrade to head)"
	@echo "  make migrate-create MSG='...'     - Create new migration"
	@echo "  make migrate-upgrade              - Upgrade to latest version"
	@echo "  make migrate-downgrade            - Downgrade one version"
	@echo "  make migrate-current              - Show current revision"
	@echo "  make migrate-history              - Show migration history"
	@echo "  make migrate-test                 - Run migration tests"
	@echo "  make validate                     - Validate migration setup"
	@echo "  make check                        - Run pre-commit checks"
	@echo "  make install                      - Install dependencies"
	@echo "  make clean                        - Clean Python cache files"
	@echo ""
	@echo "Examples:"
	@echo "  make migrate-create MSG='add user email field'"
	@echo "  make migrate-upgrade"
	@echo "  make validate"

# Install dependencies
install:
	$(PIP) install -r requirements.txt

# Validate migration setup
validate:
	$(PYTHON) validate_migrations.py

# Pre-commit checks
check:
	$(PYTHON) scripts/check_migrations.py

# Initialize database
migrate-init:
	$(PYTHON) migrate.py init

# Create new migration
migrate-create:
ifndef MSG
	@echo "Error: MSG is required"
	@echo "Usage: make migrate-create MSG='your migration message'"
	@exit 1
endif
	$(PYTHON) migrate.py create "$(MSG)"

# Upgrade database
migrate-upgrade:
	$(PYTHON) migrate.py upgrade

# Upgrade by N steps
migrate-upgrade-n:
ifndef N
	@echo "Error: N is required"
	@echo "Usage: make migrate-upgrade-n N=2"
	@exit 1
endif
	alembic upgrade +$(N)

# Downgrade database
migrate-downgrade:
	$(PYTHON) migrate.py downgrade

# Downgrade by N steps
migrate-downgrade-n:
ifndef N
	@echo "Error: N is required"
	@echo "Usage: make migrate-downgrade-n N=2"
	@exit 1
endif
	alembic downgrade -$(N)

# Show current revision
migrate-current:
	$(PYTHON) migrate.py current

# Show migration history
migrate-history:
	$(PYTHON) migrate.py history

# Run migration tests
migrate-test:
	$(PYTHON) tests/test_migrations.py

# Test upgrade/downgrade cycle
migrate-test-cycle:
	@echo "Testing migration cycle..."
	$(PYTHON) migrate.py upgrade
	@echo "✓ Upgrade successful"
	$(PYTHON) migrate.py downgrade
	@echo "✓ Downgrade successful"
	$(PYTHON) migrate.py upgrade
	@echo "✓ Re-upgrade successful"
	@echo "✅ Migration cycle test passed!"

# Clean Python cache
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.orig" -delete
	@echo "✅ Cleaned Python cache files"

# Database backup (PostgreSQL)
db-backup:
	@echo "Creating database backup..."
	@mkdir -p backups
	pg_dump -U fleetadmin -h localhost fleet_db > backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "✅ Backup created in backups/"

# Database restore (PostgreSQL)
db-restore:
ifndef FILE
	@echo "Error: FILE is required"
	@echo "Usage: make db-restore FILE=backups/backup_20231218_143000.sql"
	@exit 1
endif
	@echo "Restoring database from $(FILE)..."
	psql -U fleetadmin -h localhost -d fleet_db < $(FILE)
	@echo "✅ Database restored"

# Development workflow
dev-init: install migrate-init
	@echo "✅ Development environment initialized"

# Full test suite
test-all: validate check migrate-test
	@echo "✅ All tests passed"

# Pre-deployment checks
pre-deploy: validate check migrate-test-cycle
	@echo "✅ Ready for deployment"

# Show migration stats
stats:
	@echo "Migration Statistics:"
	@echo "  Total migrations: $$(ls -1 migrations/versions/*.py 2>/dev/null | wc -l)"
	@echo "  Current revision: $$(alembic current 2>/dev/null | grep -v 'INFO' || echo 'None')"
	@echo ""
	@echo "Database Tables:"
	@psql -U fleetadmin -h localhost -d fleet_db -c "\dt" 2>/dev/null || echo "Database not accessible"

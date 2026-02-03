# Makefile for Fleet Manager Database Migrations
# Usage: make <target>
# Example: make migrate-create MSG="add user email"

.PHONY: help migrate-init migrate-create migrate-upgrade migrate-downgrade migrate-current migrate-history migrate-test validate clean docker-cleanup docker-cleanup-auto build deploy-prod

# Default Python interpreter
PYTHON := python
PIP := pip

# Help target
help:
	@echo "Fleet Manager Makefile"
	@echo ""
	@echo "📦 Database Migration Commands:"
	@echo "  make migrate-init                 - Initialize database (upgrade to head)"
	@echo "  make migrate-create MSG='...'     - Create new migration"
	@echo "  make migrate-upgrade              - Upgrade to latest version"
	@echo "  make migrate-downgrade            - Downgrade one version"
	@echo "  make migrate-current              - Show current revision"
	@echo "  make migrate-history              - Show migration history"
	@echo "  make migrate-test                 - Run migration tests"
	@echo "  make validate                     - Validate migration setup"
	@echo "  make check                        - Run pre-commit checks"
	@echo ""
	@echo "🐳 Docker & Cleanup Commands:"
	@echo "  make docker-cleanup               - Interactive cleanup of old Docker images"
	@echo "  make docker-cleanup-auto          - Automatic cleanup of images >72h old"
	@echo "  make docker-df                    - Show Docker disk usage"
	@echo "  make build                        - Build fresh images with auto cleanup"
	@echo "  make deploy-prod                  - Deploy to production with cleanup"
	@echo ""
	@echo "📊 Monitoring Commands (FREE):"
	@echo "  make monitoring-start             - Start monitoring in production"
	@echo "  make monitoring-stop              - Stop monitoring in production"
	@echo ""
	@echo "🛠️  Utility Commands:"
	@echo "  make install                      - Install dependencies"
	@echo "  make clean                        - Clean Python cache files"
	@echo "  make db-backup                    - Backup database"
	@echo "  make pre-deploy                   - Run pre-deployment checks"
	@echo ""
	@echo "Examples:"
	@echo "  make migrate-create MSG='add user email field'"
	@echo "  make migrate-upgrade"
	@echo "  make docker-cleanup"
	@echo "  make deploy-prod"

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

# ============================================
# 🐳 Docker Cleanup & Management Commands
# ============================================

# Show Docker disk usage
docker-df:
	@echo "Docker System Disk Usage:"
	docker system df
	@echo ""
	@echo "Largest images:"
	docker images --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}" | sort -k3 -h -r | head -15

# Interactive Docker cleanup
docker-cleanup:
	@echo "Running interactive Docker cleanup..."
	@chmod +x ./cleanup_docker.sh
	@./cleanup_docker.sh

# Automatic Docker cleanup (scheduled)
docker-cleanup-auto:
	@echo "Running automatic Docker cleanup..."
	@chmod +x ./cleanup_docker_auto.sh
	@./cleanup_docker_auto.sh

# Build with automatic cleanup
build:
	@chmod +x ./build.sh
	@./build.sh

# Deploy to production with cleanup
deploy-prod:
	@chmod +x ./deploy_prod_cleanup.sh
	@./deploy_prod_cleanup.sh

# Remove dangling images only
docker-prune:
	@echo "Removing dangling images and volumes..."
	docker image prune -f
	docker volume prune -f
	@echo "✅ Cleanup complete"

# Remove all unused images
docker-prune-all:
	@echo "Removing all unused images..."
	docker image prune -a -f
	docker volume prune -f
	@echo "✅ Cleanup complete"

# Remove images older than 72 hours
docker-prune-old:
	@echo "Removing images older than 72 hours..."
	docker image prune -a -f --filter "until=72h"
	@echo "✅ Cleanup complete"

# ============================================
# 📊 Monitoring Commands (FREE)
# ============================================

# Start monitoring in production
monitoring-start:
	@chmod +x ./monitoring_start.sh
	@./monitoring_start.sh

# Stop monitoring in production
monitoring-stop:
	@chmod +x ./monitoring_stop.sh
	@./monitoring_stop.sh


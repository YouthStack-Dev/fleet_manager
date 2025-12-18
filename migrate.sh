#!/bin/bash
# Migration management script for Unix-based systems

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Function to show help
show_help() {
    cat << EOF
🗄️  Fleet Manager Migration Tool

Usage: ./migrate.sh <command> [options]

Commands:
  init              Initialize database with all migrations (upgrade to head)
  create <message>  Create a new migration with autogenerate
  upgrade [rev]     Upgrade to a specific revision (default: head)
  downgrade [rev]   Downgrade to a specific revision (default: -1)
  current           Show current database revision
  history           Show all migration history
  heads             Show head revisions
  stamp <rev>       Mark database as being at a specific revision without running migrations
  help              Show this help message

Examples:
  ./migrate.sh init
  ./migrate.sh create "add user email column"
  ./migrate.sh upgrade
  ./migrate.sh upgrade +2
  ./migrate.sh downgrade -1
  ./migrate.sh current
  ./migrate.sh history
  ./migrate.sh stamp head

For more information, see: docs/MIGRATION_GUIDE.md
EOF
}

# Check if alembic is installed
check_alembic() {
    if ! command -v alembic &> /dev/null; then
        print_error "Alembic is not installed. Please install it using: pip install alembic"
        exit 1
    fi
}

# Initialize migrations
init_migrations() {
    print_info "Initializing database..."
    alembic upgrade head
    print_success "Database initialized successfully!"
}

# Create new migration
create_migration() {
    if [ -z "$2" ]; then
        print_error "Please provide a message for the migration"
        echo "Usage: ./migrate.sh create 'add new column to users'"
        exit 1
    fi
    
    message="$2"
    print_info "Creating new migration: $message"
    alembic revision --autogenerate -m "$message"
    print_success "Migration created successfully!"
    print_warning "Please review the generated migration file before applying it"
}

# Upgrade database
upgrade_database() {
    revision=${2:-head}
    print_info "Upgrading database to: $revision"
    alembic upgrade "$revision"
    print_success "Database upgraded successfully!"
}

# Downgrade database
downgrade_database() {
    revision=${2:--1}
    print_info "Downgrading database to: $revision"
    alembic downgrade "$revision"
    print_success "Database downgraded successfully!"
}

# Show current revision
show_current() {
    print_info "Current database revision:"
    alembic current
}

# Show history
show_history() {
    print_info "Migration history:"
    alembic history --verbose
}

# Show heads
show_heads() {
    print_info "Head revisions:"
    alembic heads --verbose
}

# Stamp database
stamp_database() {
    if [ -z "$2" ]; then
        print_error "Please provide a revision to stamp"
        echo "Usage: ./migrate.sh stamp <revision>"
        exit 1
    fi
    
    revision="$2"
    print_info "Stamping database at revision: $revision"
    alembic stamp "$revision"
    print_success "Database stamped successfully!"
}

# Main script
check_alembic

case "${1:-help}" in
    init)
        init_migrations
        ;;
    create)
        create_migration "$@"
        ;;
    upgrade)
        upgrade_database "$@"
        ;;
    downgrade)
        downgrade_database "$@"
        ;;
    current)
        show_current
        ;;
    history)
        show_history
        ;;
    heads)
        show_heads
        ;;
    stamp)
        stamp_database "$@"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac

# Migration Setup - Quick Reference

## ✅ Migration Setup Complete!

Your Fleet Manager project now has a fully configured migration system using Alembic.

## 📁 Files Created

```
fleet_manager/
├── alembic.ini                     # Alembic configuration
├── migrate.py                      # Python migration helper (cross-platform)
├── migrate.sh                      # Bash migration helper (Linux/Mac)
├── validate_migrations.py          # Quick validation script
├── migrations/
│   ├── env.py                     # Migration environment config
│   ├── script.py.mako            # Migration template
│   └── versions/                  # Your migration files
│       └── 20251218_*.py         # Initial migration (ready to customize)
├── docs/
│   └── MIGRATION_GUIDE.md        # Complete migration documentation
└── tests/
    └── test_migrations.py        # Migration test suite
```

## 🚀 Quick Start

### 1. Configure Database

Ensure your `.env` file has database credentials:

```env
POSTGRES_HOST=localhost
POSTGRES_USER=fleetadmin
POSTGRES_PASSWORD=your_password_here
POSTGRES_DB=fleet_db
PORT=5432
```

### 2. Review & Customize Initial Migration

The initial migration was created but needs your tables defined. 

**Option A: Auto-generate from models (when DB is available)**
```bash
# Delete the empty migration
rm migrations/versions/20251218_*.py

# Create new with autogenerate (requires DB connection)
python migrate.py create "initial database schema"
```

**Option B: Use existing create_tables.py logic**
If you have `app/database/create_tables.py`, you can use that logic.

### 3. Apply Migrations

```bash
# Apply all migrations
python migrate.py init

# Or manually
alembic upgrade head
```

## 📚 Common Commands

### Create a New Migration
```bash
# Auto-detect changes
python migrate.py create "add user email field"

# Manual migration
alembic revision -m "custom migration"
```

### Apply Migrations
```bash
# Upgrade to latest
python migrate.py upgrade

# Upgrade by steps
python migrate.py upgrade +2

# Upgrade to specific revision
python migrate.py upgrade abc123
```

### Rollback Migrations
```bash
# Downgrade one step
python migrate.py downgrade

# Downgrade to specific revision
python migrate.py downgrade abc123
```

### Check Status
```bash
# Current revision
python migrate.py current

# Migration history
python migrate.py history

# Head revisions
python migrate.py heads
```

## 🔍 Validate Setup

Run the validation script anytime:

```bash
python validate_migrations.py
```

## 📖 Full Documentation

See [docs/MIGRATION_GUIDE.md](docs/MIGRATION_GUIDE.md) for:
- Detailed commands
- Best practices
- Troubleshooting
- Production deployment
- Advanced features

## 🧪 Testing

Run migration tests:

```bash
# Full test suite
python tests/test_migrations.py

# Quick validation
python validate_migrations.py
```

## ⚙️ Configuration

### Offline Mode

If you don't have database access during migration creation:

```bash
# Create manual migration
alembic revision -m "my migration"

# Edit the generated file to add upgrade/downgrade logic
```

### Autogenerate Mode

Requires database connection but automatically detects schema changes:

```bash
# Alembic compares models vs database
python migrate.py create "describe changes"
```

## 🎯 Next Steps

1. ✅ **Setup Complete** - Migration infrastructure is ready
2. 📝 **Create Migrations** - Define your initial schema or auto-generate
3. 🧪 **Test Migrations** - Run upgrade/downgrade cycles
4. 🚀 **Deploy** - Apply to dev, staging, then production

## 💡 Tips

- **Always review** auto-generated migrations before applying
- **Test both ways**: upgrade AND downgrade
- **Use meaningful messages** in migration names
- **Keep migrations small** and focused
- **Never edit** migrations that have been applied to production

## 🆘 Troubleshooting

### Database Connection Issues

If you see "password authentication failed":
1. Check your `.env` file
2. Verify PostgreSQL is running
3. Test connection: `psql -U fleetadmin -d fleet_db`

### Import Errors

If models can't be imported:
1. Check `migrations/env.py` imports
2. Ensure all models inherit from `Base`
3. Run: `python validate_migrations.py`

### Out of Sync

If database doesn't match migrations:
```bash
# Mark database at current state (doesn't run migrations)
alembic stamp head
```

## 📞 Support

For detailed help:
- See [docs/MIGRATION_GUIDE.md](docs/MIGRATION_GUIDE.md)
- Run `python migrate.py help`
- Check Alembic docs: https://alembic.sqlalchemy.org/

---

**Status**: ✅ Ready to use
**Version**: 1.0.0
**Date**: December 2025

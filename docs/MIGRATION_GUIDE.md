# Database Migration Guide

## Overview

This project uses **Alembic** for database schema migrations, providing a scalable and version-controlled approach to database changes.

## Table of Contents

- [Quick Start](#quick-start)
- [Migration Commands](#migration-commands)
- [Creating Migrations](#creating-migrations)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)
- [Production Deployment](#production-deployment)

---

## Quick Start

### Initial Setup

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Database**
   Ensure your `.env` file has the correct database connection:
   ```env
   POSTGRES_HOST=localhost
   POSTGRES_USER=fleetadmin
   POSTGRES_PASSWORD=fleetpass
   POSTGRES_DB=fleet_db
   PORT=5432
   ```

3. **Initialize Database**
   ```bash
   # On Windows
   python migrate.py init
   
   # On Linux/Mac
   ./migrate.sh init
   ```

---

## Migration Commands

### Using Python Script (Cross-Platform)

```bash
# Initialize database (apply all migrations)
python migrate.py init

# Create a new migration
python migrate.py create "add email column to users"

# Upgrade to latest version
python migrate.py upgrade

# Upgrade by specific steps
python migrate.py upgrade +2

# Downgrade one version
python migrate.py downgrade

# Downgrade to specific revision
python migrate.py downgrade abc123

# Show current revision
python migrate.py current

# Show migration history
python migrate.py history

# Show head revisions
python migrate.py heads

# Show help
python migrate.py help
```

### Using Shell Script (Linux/Mac)

```bash
# Make script executable (first time only)
chmod +x migrate.sh

# Use same commands as Python script
./migrate.sh init
./migrate.sh create "add email column to users"
./migrate.sh upgrade
# ... etc
```

### Direct Alembic Commands

```bash
# Create migration manually (without autogenerate)
alembic revision -m "add new table"

# Upgrade to head
alembic upgrade head

# Downgrade one revision
alembic downgrade -1

# Show current revision
alembic current

# Show full history
alembic history --verbose

# Stamp database at revision (mark without running)
alembic stamp head
```

---

## Creating Migrations

### Auto-Generate Migrations (Recommended)

Alembic can automatically detect model changes:

```bash
python migrate.py create "describe your changes here"
```

**Example:**
```bash
python migrate.py create "add phone number to driver table"
```

This will:
1. Compare your SQLAlchemy models with the database
2. Generate a migration file in `migrations/versions/`
3. Include upgrade and downgrade functions

### Manual Migrations

For complex changes, you may need to edit migrations manually:

1. Create the migration:
   ```bash
   alembic revision -m "custom migration"
   ```

2. Edit the generated file in `migrations/versions/`:
   ```python
   def upgrade() -> None:
       op.add_column('drivers',
           sa.Column('phone_number', sa.String(20), nullable=True)
       )
       op.create_index('idx_driver_phone', 'drivers', ['phone_number'])
   
   def downgrade() -> None:
       op.drop_index('idx_driver_phone', 'drivers')
       op.drop_column('drivers', 'phone_number')
   ```

### Migration File Naming

Migration files are automatically named with timestamp:
```
20231218_1430_abc123def456_add_phone_number_to_driver.py
```

Format: `YYYYMMDD_HHMM_<revision>_<slug>.py`

---

## Best Practices

### ✅ Do's

1. **Always Review Auto-Generated Migrations**
   - Check the generated SQL
   - Ensure data migrations are handled
   - Verify indexes and constraints

2. **Test Migrations Both Ways**
   ```bash
   python migrate.py upgrade    # Test upgrade
   python migrate.py downgrade  # Test downgrade
   python migrate.py upgrade    # Apply again
   ```

3. **Use Meaningful Messages**
   ```bash
   # Good ✅
   python migrate.py create "add driver certification expiry date"
   
   # Bad ❌
   python migrate.py create "update table"
   ```

4. **Include Data Migrations**
   ```python
   def upgrade() -> None:
       # Schema change
       op.add_column('users', sa.Column('status', sa.String(20)))
       
       # Data migration
       op.execute("UPDATE users SET status = 'active' WHERE deleted_at IS NULL")
       op.execute("UPDATE users SET status = 'deleted' WHERE deleted_at IS NOT NULL")
   ```

5. **Handle Nullable Constraints Carefully**
   ```python
   def upgrade() -> None:
       # Add column as nullable first
       op.add_column('users', sa.Column('email', sa.String(255), nullable=True))
       
       # Set default values
       op.execute("UPDATE users SET email = CONCAT(username, '@example.com')")
       
       # Make it non-nullable
       op.alter_column('users', 'email', nullable=False)
   ```

### ❌ Don'ts

1. **Never Edit Applied Migrations**
   - Create a new migration instead
   - Editing applied migrations breaks version control

2. **Don't Skip Migration Testing**
   - Always test on dev/staging before production
   - Verify data integrity after migration

3. **Avoid Direct Database Changes**
   - All schema changes should go through migrations
   - Manual changes will cause version conflicts

4. **Don't Forget Downgrade Logic**
   - Every migration should be reversible
   - Test downgrade paths

---

## Troubleshooting

### Migration Conflicts

**Problem:** "Can't locate revision identified by 'abc123'"

**Solution:**
```bash
# Check current state
python migrate.py current

# View history
python migrate.py history

# Stamp at correct revision
alembic stamp head
```

### Out of Sync Database

**Problem:** Database doesn't match migrations

**Solution 1: Clean Start (Development Only)**
```bash
# Drop all tables
# WARNING: This deletes all data!

# Then run migrations
python migrate.py init
```

**Solution 2: Manual Sync**
```bash
# Mark database as current without running migrations
alembic stamp head
```

### Autogenerate Not Detecting Changes

**Problem:** `alembic revision --autogenerate` finds no changes

**Solutions:**
1. Ensure all models are imported in `migrations/env.py`
2. Check that model changes are saved
3. Verify database connection

### Database Connection Errors

**Problem:** Can't connect to database

**Solutions:**
1. Check `.env` configuration
2. Ensure database is running
3. Verify credentials
4. Check firewall/network settings

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] All migrations tested in staging
- [ ] Backup database created
- [ ] Rollback plan documented
- [ ] Migration time estimated
- [ ] Team notified of downtime (if any)
- [ ] Health checks prepared

### Deployment Steps

1. **Backup Database**
   ```bash
   pg_dump -U fleetadmin -h localhost fleet_db > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **Apply Migrations**
   ```bash
   # Set production environment
   export ENV=production
   
   # Run migrations
   python migrate.py upgrade
   ```

3. **Verify Success**
   ```bash
   # Check current revision
   python migrate.py current
   
   # Verify critical tables
   psql -U fleetadmin -d fleet_db -c "\dt"
   ```

4. **Monitor Application**
   - Check application logs
   - Verify API endpoints
   - Test critical workflows

### Zero-Downtime Migrations

For large tables or production systems:

1. **Phase 1: Add (Backward Compatible)**
   ```python
   # Migration 1: Add new column as nullable
   def upgrade():
       op.add_column('users', sa.Column('new_field', sa.String(100), nullable=True))
   ```

2. **Deploy Application** (supports both old and new schema)

3. **Phase 2: Populate Data**
   ```python
   # Migration 2: Populate new column
   def upgrade():
       op.execute("UPDATE users SET new_field = old_field || '_migrated'")
   ```

4. **Phase 3: Enforce (Breaking Change)**
   ```python
   # Migration 3: Make non-nullable, drop old column
   def upgrade():
       op.alter_column('users', 'new_field', nullable=False)
       op.drop_column('users', 'old_field')
   ```

5. **Deploy Updated Application**

### Rollback Procedure

If migration fails:

```bash
# Downgrade to previous revision
python migrate.py downgrade -1

# Or specific revision
python migrate.py downgrade abc123

# Restore from backup if needed
psql -U fleetadmin -d fleet_db < backup_20231218_143000.sql
```

---

## Advanced Usage

### Multiple Heads (Branching)

When working with feature branches:

```bash
# Create branch
alembic revision -m "feature branch" --branch-label feature_x

# Merge branches
alembic merge -m "merge feature" <rev1> <rev2>
```

### Conditional Migrations

```python
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

def upgrade() -> None:
    # Check if column exists
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns('users')]
    
    if 'email' not in columns:
        op.add_column('users', sa.Column('email', sa.String(255)))
```

### Custom Migration Context

Edit `migrations/env.py` to customize:

```python
# Include/exclude schemas
context.configure(
    target_metadata=target_metadata,
    include_schemas=True,
    version_table_schema='public'
)

# Custom naming conventions
context.configure(
    target_metadata=target_metadata,
    render_as_batch=True,  # For SQLite
    compare_type=True,
    compare_server_default=True
)
```

---

## Directory Structure

```
fleet_manager/
├── alembic.ini                    # Alembic configuration
├── migrate.py                     # Python migration script
├── migrate.sh                     # Shell migration script
├── migrations/
│   ├── env.py                    # Environment configuration
│   ├── script.py.mako           # Migration template
│   └── versions/                # Migration files
│       ├── 20231218_1430_abc123_initial.py
│       └── 20231219_1015_def456_add_driver_phone.py
└── app/
    └── models/                   # SQLAlchemy models
```

---

## Environment Variables

Key variables for migrations:

```env
# Database connection
DATABASE_URL=postgresql://user:pass@host:port/dbname
POSTGRES_HOST=localhost
POSTGRES_USER=fleetadmin
POSTGRES_PASSWORD=fleetpass
POSTGRES_DB=fleet_db
PORT=5432

# Environment
ENV=development  # development, dev-server, production
```

---

## Additional Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Database Migration Best Practices](https://www.postgresql.org/docs/current/ddl.html)

---

## Support

For issues or questions:
1. Check existing migrations: `python migrate.py history`
2. Review logs in console output
3. Consult team documentation
4. Check database logs

## Maintenance

### Regular Tasks

- Review and clean up old migrations periodically
- Document complex migrations
- Keep migration history linear when possible
- Test migrations in all environments

---

**Last Updated:** December 2025
**Version:** 1.0.0

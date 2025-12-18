# Production Database Migration Deployment

This guide explains how to deploy database migrations to your production environment.

## Prerequisites

- Docker and Docker Compose installed
- Production database configured (PostgreSQL 15)
- SSH access to production server (if remote)
- Backup of production database created

## Production Database Connection

Your production setup uses:
- **Host**: `fleet_postgres` (Docker) or your server IP
- **Port**: `5434` (mapped from 5432)
- **User**: `fleetadmin`
- **Password**: `fleetpass` (from docker-compose_prod.yaml)
- **Database**: `fleet_db`

## Deployment Options

### Option 1: Docker-Based Deployment (Recommended)

If your production runs in Docker:

```bash
# 1. Navigate to your fleet_manager directory
cd /path/to/fleet_manager

# 2. Start production environment
docker-compose -f docker-compose_prod.yaml up -d

# 3. Wait for database to be healthy (check health status)
docker ps --filter "name=fleet_postgres" --format "table {{.Names}}\t{{.Status}}"

# 4. Run migrations in container
docker exec -it service_manager python migrate.py upgrade head

# 5. Verify migration success
docker exec -it service_manager python migrate.py current
docker exec -it service_manager python migrate.py history
```

### Option 2: Direct Server Deployment (SSH)

If you have SSH access to production server:

```bash
# 1. SSH into production server
ssh user@production-server

# 2. Navigate to project
cd /path/to/fleet_manager

# 3. Activate Python environment
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# 4. Run migrations
python migrate.py upgrade head

# 5. Verify
python migrate.py current
python migrate.py history
```

### Option 3: Environment Variable Method

If you want to target a specific database without changing code:

```bash
# On local machine, target remote production database
export POSTGRES_HOST=your-production-server.com
export POSTGRES_USER=fleetadmin
export POSTGRES_PASSWORD=your_secure_password
export POSTGRES_DB=fleet_db
export POSTGRES_PORT=5434

# Run migrations
python migrate.py upgrade head
```

## Pre-Deployment Checklist

- [ ] **Backup Production Database**
  ```bash
  # Local backup
  pg_dump -U fleetadmin -h localhost -p 5434 fleet_db > backup_prod_$(date +%Y%m%d_%H%M%S).sql
  
  # Or via Docker
  docker exec fleet_postgres pg_dump -U fleetadmin fleet_db > backup_prod_$(date +%Y%m%d_%H%M%S).sql
  ```

- [ ] **Test Migrations in Staging First**
  - Create a staging database with production data backup
  - Run migrations on staging
  - Verify application works
  - Document any issues

- [ ] **Review Migration Files**
  ```bash
  python migrate.py history
  ```

- [ ] **Verify Database Connection**
  ```bash
  python -c "from app.config import settings; print(f'Target DB: {settings.DATABASE_URL}')"
  ```

- [ ] **Estimate Migration Duration**
  - Check migration file for large operations
  - Review table sizes in production

- [ ] **Plan Rollback Strategy**
  - Know the previous revision ID
  - Have rollback command ready: `python migrate.py downgrade -1`

## Deployment Steps

### Step 1: Backup Database
```bash
# Docker method
docker exec fleet_postgres pg_dump -U fleetadmin fleet_db > backup_prod_$(date +%Y%m%d_%H%M%S).sql

# Direct method
pg_dump -U fleetadmin -h production-server -p 5434 fleet_db > backup_prod_$(date +%Y%m%d_%H%M%S).sql
```

### Step 2: Review Pending Migrations
```bash
# Show migrations not yet applied
python migrate.py history

# Example output:
# Rev: new_migration_123 (head)
# Parent: b75d731987dd
#   Add new feature column
#
# Rev: b75d731987dd
# Parent: <base>
#   initial database schema
```

### Step 3: Run Migrations
```bash
# For Docker:
docker exec -it service_manager python migrate.py upgrade head

# For direct server access:
python migrate.py upgrade head
```

### Step 4: Verify Success
```bash
# Check current revision
python migrate.py current
# Expected: <latest_revision> (head)

# Check history
python migrate.py history

# Verify tables exist
python -c "
from app.database.session import engine
import sqlalchemy
inspector = sqlalchemy.inspect(engine)
tables = inspector.get_table_names()
print(f'✅ Database has {len(tables)} tables')
for table in sorted(tables):
    print(f'  ✓ {table}')
"
```

### Step 5: Monitor Application
```bash
# Check application logs
docker logs -f service_manager

# Test API endpoints
curl http://your-server/api/health
curl http://your-server/api/status
```

### Step 6: Rollback (If Needed)
```bash
# If migration fails, rollback
python migrate.py downgrade -1

# Restore from backup if necessary
psql -U fleetadmin -h localhost -p 5434 fleet_db < backup_prod_20231218_143000.sql
```

## Production Migration Checklist

| Item | Status | Notes |
|------|--------|-------|
| Database backed up | ⬜ | Store in safe location |
| Migration tested in staging | ⬜ | Verify on copy of prod data |
| Maintenance window scheduled | ⬜ | Notify users if needed |
| Rollback plan documented | ⬜ | Know previous revision |
| Team notified | ⬜ | Inform stakeholders |
| Monitoring active | ⬜ | Watch for errors |
| Performance baseline | ⬜ | Compare before/after |

## Common Issues

### Issue 1: Connection Refused
**Problem**: Can't connect to production database
**Solution**:
1. Verify database is running: `docker ps | grep fleet_postgres`
2. Check credentials in `.env` or docker-compose file
3. Verify network connectivity: `ping production-server`
4. Check firewall rules for port 5434

### Issue 2: Migration Fails Midway
**Problem**: Migration starts but fails partway through
**Solution**:
1. Check database logs: `docker logs fleet_postgres`
2. Check application logs: `docker logs service_manager`
3. Rollback: `python migrate.py downgrade -1`
4. Review migration file for issues
5. Fix and create new migration

### Issue 3: Application Won't Start After Migration
**Problem**: App crashes with database errors after migration
**Solution**:
1. Rollback migration: `python migrate.py downgrade -1`
2. Verify schema with: `python migrate.py current`
3. Check if app code needs update to work with new schema
4. Redeploy app version that supports new schema

### Issue 4: Out of Memory During Large Migration
**Problem**: Migration runs out of memory on large tables
**Solution**:
1. Stop application to free resources
2. Increase server memory if possible
3. Use batching in migration if applicable
4. Break into smaller migrations

## Zero-Downtime Migration Strategy

For production systems that can't have downtime:

### Phase 1: Additive Changes (No downtime)
```bash
# New columns, tables, indexes can be added without downtime
python migrate.py upgrade head
# Application continues running with old schema
```

### Phase 2: Deploy Updated Application
```bash
# Blue-green deployment
# Old version still running (knows about new columns)
# New version deployed (uses new schema)
docker-compose -f docker-compose_prod.yaml up -d --build
```

### Phase 3: Cleanup (Later)
```bash
# After all old versions are retired, remove deprecated columns
python migrate.py upgrade head
```

## Monitoring After Deployment

### Check Query Performance
```sql
-- SSH into database
psql -U fleetadmin -h production-server -p 5434 fleet_db

-- Check table sizes
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Check indexes
SELECT * FROM pg_stat_user_indexes;
```

### Monitor Application Performance
```bash
# Check response times
curl -w "@curl_format.txt" -o /dev/null -s http://your-server/api/health

# Monitor resource usage
docker stats service_manager
```

## Maintenance

### Regular Tasks
- Review migration history monthly
- Clean up old backup files
- Document any custom migrations
- Test disaster recovery procedures

### Migration History Management
```bash
# View all migrations
python migrate.py history

# Document new migrations
git log --oneline migrations/versions/

# Archive old backups
tar -czf backups/archive_$(date +%Y%m).tar.gz backups/*.sql
```

## Support & Troubleshooting

For detailed help:
1. Check migration logs: `docker logs service_manager`
2. Review migration file: `migrations/versions/<migration_file>`
3. Check database logs: `docker logs fleet_postgres`
4. Consult main [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)
5. Reference [Alembic docs](https://alembic.sqlalchemy.org/)

---

**Last Updated**: December 2025
**Alembic Version**: 1.14+
**PostgreSQL Version**: 15
**Production Status**: ✅ Ready for Deployment


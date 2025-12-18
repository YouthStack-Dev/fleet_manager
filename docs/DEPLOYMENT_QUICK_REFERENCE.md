# Production Deployment Quick Reference

## 🚀 Quick Start Commands

### Verify Database Connection
```bash
python deploy_prod.py --verify
```

### Backup Production Database Only
```bash
python deploy_prod.py --backup
```

### Verify + Backup + Deploy (Full Process)
```bash
python deploy_prod.py --deploy
```

### Deploy Using Docker
```bash
python deploy_prod.py --deploy --docker
```

### Rollback Last Migration (Emergency)
```bash
python deploy_prod.py --rollback
```

### Rollback 2 Migrations
```bash
python deploy_prod.py --rollback 2
```

---

## 📋 Deployment Scenarios

### Scenario 1: Local Development Database (Port 5434)
```bash
# This is your current setup
python migrate.py upgrade head
python migrate.py current
```

### Scenario 2: Docker Production Environment
```bash
# Your docker-compose_prod.yaml setup
docker-compose -f docker-compose_prod.yaml up -d

# Deploy migrations
python deploy_prod.py --deploy --docker

# Or manually
docker exec -it service_manager python migrate.py upgrade head
```

### Scenario 3: Remote Production Server
```bash
# Option A: SSH into server and run migrations
ssh user@production-server
cd /path/to/fleet_manager
python migrate.py upgrade head

# Option B: Target remote database from local machine
export POSTGRES_HOST=production-server.com
export POSTGRES_PORT=5434
python deploy_prod.py --deploy
```

### Scenario 4: Multiple Environments
```bash
# Development
python migrate.py upgrade head

# Staging (test with production database backup)
export POSTGRES_HOST=staging-server
export POSTGRES_DB=fleet_staging
python migrate.py upgrade head

# Production
export POSTGRES_HOST=prod-server
python deploy_prod.py --deploy
```

---

## ⚠️ Important Notes

### Before Any Deployment:

✅ **Always backup first**
```bash
python deploy_prod.py --backup
```

✅ **Verify connection works**
```bash
python deploy_prod.py --verify
```

✅ **Review migrations**
```bash
python migrate.py history
```

### Safety Measures:

- **Backups** are automatically saved to `backups/` directory
- **Rollback** is always available: `python deploy_prod.py --rollback`
- **Verify** after deployment: `python migrate.py current`
- **Monitor** application logs after deployment

### Docker Deployment:

```bash
# Your setup in docker-compose_prod.yaml:
- POSTGRES_USER: fleetadmin
- POSTGRES_PASSWORD: fleetpass
- POSTGRES_DB: fleet_db
- Port: 5434 → 5432

# Deployment command:
python deploy_prod.py --deploy --docker
```

---

## 📊 Typical Deployment Workflow

```
1. Test locally ✅
   ├─ python migrate.py upgrade head
   └─ python migrate.py current

2. Backup production 🔒
   ├─ python deploy_prod.py --backup
   └─ Verify backup in backups/

3. Verify connection 🔗
   └─ python deploy_prod.py --verify

4. Deploy to production 🚀
   ├─ python deploy_prod.py --deploy
   └─ OR: docker exec service_manager python migrate.py upgrade head

5. Verify deployment ✅
   ├─ python deploy_prod.py --verify
   └─ python migrate.py current

6. Monitor application 👀
   ├─ Check logs: docker logs service_manager
   └─ Test API endpoints
```

---

## 🔧 Manual Deployment (If Script Fails)

```bash
# Step 1: Backup
pg_dump -U fleetadmin -h production-server -p 5434 fleet_db > backup.sql

# Step 2: Connect to database
psql -U fleetadmin -h production-server -p 5434 -d fleet_db

# Step 3: Check current state
python migrate.py current

# Step 4: Apply migrations
python migrate.py upgrade head

# Step 5: Verify
python migrate.py current
python migrate.py history

# Step 6: Rollback if needed
python migrate.py downgrade -1
```

---

## 🆘 Emergency Procedures

### Migration Failed - Rollback:
```bash
# Immediate rollback
python migrate.py downgrade -1

# Multiple rollbacks
python migrate.py downgrade -3

# Rollback to specific revision
python migrate.py downgrade abc123def456
```

### Restore from Backup:
```bash
# If database corruption, restore backup
psql -U fleetadmin -h production-server -p 5434 -d fleet_db < backup_prod_20231218_143000.sql
```

### Reset to Head:
```bash
# Mark database as being at head (without running migrations)
alembic stamp head
```

---

## 📈 Post-Deployment Verification

```bash
# Check all tables exist
python -c "
from app.database.session import engine
import sqlalchemy
inspector = sqlalchemy.inspect(engine)
print(f'Tables: {len(inspector.get_table_names())}')
for table in sorted(inspector.get_table_names()):
    print(f'  ✓ {table}')
"

# Check migration applied
python migrate.py current

# View history
python migrate.py history

# Monitor logs (if Docker)
docker logs -f service_manager
```

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Can't connect to database | Verify POSTGRES_HOST, POSTGRES_PORT, credentials |
| Migration fails midway | Check database logs, rollback, investigate |
| Tables already exist error | Run `alembic stamp head` to mark as migrated |
| Out of memory during migration | Stop other processes, increase server memory |
| Application won't start | Check if app version matches schema, rollback if needed |

---

## 📞 Support

For help:
1. See full guide: [docs/PRODUCTION_DEPLOYMENT.md](docs/PRODUCTION_DEPLOYMENT.md)
2. Check logs: `docker logs service_manager` or `docker logs fleet_postgres`
3. Review migration: `python migrate.py history`
4. Alembic docs: https://alembic.sqlalchemy.org/

---

**Last Updated**: December 2025
**Ready for Production**: ✅


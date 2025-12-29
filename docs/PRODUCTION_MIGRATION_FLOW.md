# Production Migration Flow - Automatic Deployment

## 🔄 What Happens When You Deploy to Production

### Trigger
When you push to the `main` branch or manually trigger the workflow, the GitHub Actions workflow executes:

## 📋 Deployment Steps

### 1️⃣ Build Phase
```bash
✓ Checkout code from main branch
✓ Build Docker image: dheerajkumarp/fleet_service_manager:latest
✓ Push to Docker Hub
```

### 2️⃣ Pre-Deployment Phase
```bash
✓ Copy docker-compose_prod.yaml to VPS
✓ SSH into VPS server
✓ Create environment files (service.prod.env)
✓ Setup Firebase credentials
✓ **BACKUP DATABASE** (pg_dump to ~/backups/backup_YYYYMMDD_HHMMSS.sql)
```

### 3️⃣ Container Deployment
```bash
✓ Stop running containers
✓ Pull latest Docker image
✓ Start containers with docker-compose up -d
✓ Wait 10 seconds for containers to be healthy
```

### 4️⃣ **DATABASE MIGRATION** (NEW! ✅)
```bash
✓ Check current migration state
✓ Show migration history
✓ Run: docker exec service_manager python migrate.py upgrade head
✓ Verify migration success
✓ Check database tables
```

### 5️⃣ Verification Phase
```bash
✓ Verify migration current state
✓ List all database tables
✓ Display deployment success message
```

---

## 🎯 Migration Commands Executed

### On Every Production Deployment:

```bash
# 1. Backup database
docker exec fleet_postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup.sql

# 2. Show current state
docker exec service_manager python migrate.py current

# 3. Show pending migrations
docker exec service_manager python migrate.py history

# 4. Apply migrations
docker exec service_manager python migrate.py upgrade head

# 5. Verify success
docker exec service_manager python migrate.py current

# 6. Check tables
docker exec fleet_postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -c "\dt"
```

---

## 🔒 Safety Features

### 1. **Automatic Backup**
- Database backed up to `~/backups/` before every deployment
- Backup naming: `backup_YYYYMMDD_HHMMSS.sql`
- Stored on VPS server for recovery

### 2. **Migration Failure Handling**
```bash
# If migration fails:
→ Show error message
→ Display container logs
→ Exit with error code
→ Deployment marked as failed
```

### 3. **Manual Rollback Available**
```bash
# SSH into VPS
ssh user@vps

# Rollback one migration
docker exec service_manager python migrate.py downgrade -1

# Or restore from backup
cat ~/backups/backup_20231218_143000.sql | \
  docker exec -i fleet_postgres psql -U fleetadmin -d fleet_db
```

---

## 📊 Migration Workflow Comparison

### BEFORE (Broken - No Migrations):
```
Push to main
    ↓
Build image
    ↓
Deploy containers
    ↓
❌ Database schema NOT updated
❌ Application may crash with schema errors
```

### AFTER (Fixed - With Migrations):
```
Push to main
    ↓
Build image
    ↓
Backup database
    ↓
Deploy containers
    ↓
✅ Run migrations
    ↓
✅ Verify success
    ↓
✅ Application uses latest schema
```

---

## 🚀 How to Deploy

### Automatic Deployment (Recommended)
```bash
# 1. Merge your changes to main
git checkout main
git merge feat-all
git push origin main

# 2. GitHub Actions automatically:
#    - Builds image
#    - Backs up database
#    - Deploys containers
#    - Runs migrations
#    - Verifies success
```

### Manual Deployment (If Needed)
```bash
# Trigger workflow manually from GitHub
# Go to: Actions → Deploy Fleet Manager → Run workflow
# Select: main branch
```

---

## 🔍 Monitoring Deployments

### Check GitHub Actions
1. Go to: https://github.com/YouthStack-Dev/fleet_manager/actions
2. Find latest "Deploy Fleet Manager" workflow
3. Check logs for migration output

### Check on VPS
```bash
# SSH into VPS
ssh user@your-vps-ip

# Check container status
docker ps

# Check migration state
docker exec service_manager python migrate.py current

# Check application logs
docker logs service_manager

# Check database tables
docker exec fleet_postgres psql -U fleetadmin -d fleet_db -c "\dt"
```

---

## 📝 Migration Log Example

When deployment runs, you'll see:

```
Creating database backup...
Backup saved to: ~/backups/backup_20231218_143021.sql

Stopping containers...
Pulling latest image...
Starting containers...

Waiting for containers to be ready...
Current migration state:
b75d731987dd (head)

Migration history:
Rev: b75d731987dd (head)
Parent: <base>
  initial database schema

Running database migrations...
INFO  [alembic.runtime.migration] Running upgrade  -> b75d731987dd, initial database schema
Success: Migrations applied

Verifying migration status...
b75d731987dd (head)

Verifying database tables...
                 List of relations
 Schema |           Name           | Type  |   Owner
--------+--------------------------+-------+------------
 public | admin                    | table | fleetadmin
 public | drivers                  | table | fleetadmin
 public | bookings                 | table | fleetadmin
 ...

Deployment completed successfully!
```

---

## ⚠️ Important Notes

### Database Migrations Are Now Automatic
- ✅ Every push to `main` applies migrations
- ✅ Backups created before each deployment
- ✅ Rollback available if needed

### First Deployment to Existing Database
If your production database already has tables:
```bash
# SSH into VPS after first deployment
ssh user@vps

# Mark database as migrated (one-time only)
docker exec service_manager alembic stamp head
```

### Future Schema Changes
1. Make model changes in `app/models/`
2. Create migration locally: `python migrate.py create "description"`
3. Test locally: `python migrate.py upgrade`
4. Commit and push to main
5. GitHub Actions automatically deploys and migrates

---

## 🆘 Troubleshooting

### Migration Fails on Deployment
```bash
# 1. Check GitHub Actions logs
# 2. SSH into VPS
ssh user@vps

# 3. Check container logs
docker logs service_manager

# 4. Check migration state
docker exec service_manager python migrate.py current

# 5. Manual rollback if needed
docker exec service_manager python migrate.py downgrade -1

# 6. Or restore backup
cat ~/backups/backup_latest.sql | docker exec -i fleet_postgres psql -U fleetadmin -d fleet_db
```

### Database Connection Issues
```bash
# Verify database is running
docker ps | grep fleet_postgres

# Check database logs
docker logs fleet_postgres

# Test connection
docker exec fleet_postgres psql -U fleetadmin -d fleet_db -c "SELECT version()"
```

### Migration Already Applied
```bash
# If migration shows as already applied, verify state
docker exec service_manager python migrate.py current
docker exec service_manager python migrate.py history

# If out of sync, stamp at current state
docker exec service_manager alembic stamp head
```

---

## 📈 Best Practices

### Before Merging to Main
1. ✅ Test migrations locally
2. ✅ Test on staging environment
3. ✅ Review migration file
4. ✅ Ensure rollback logic exists
5. ✅ Document breaking changes

### During Deployment
1. ✅ Monitor GitHub Actions logs
2. ✅ Watch for migration output
3. ✅ Verify deployment success
4. ✅ Test application endpoints

### After Deployment
1. ✅ Check migration state on VPS
2. ✅ Verify database tables
3. ✅ Test critical features
4. ✅ Monitor error logs

---

## 🔗 Related Documentation

- [Production Deployment Guide](PRODUCTION_DEPLOYMENT.md)
- [Migration Guide](MIGRATION_GUIDE.md)
- [Deployment Quick Reference](DEPLOYMENT_QUICK_REFERENCE.md)

---

**Last Updated**: December 18, 2025
**Status**: ✅ Migrations Automated in Production
**Workflow**: `.github/workflows/deploy.yaml`


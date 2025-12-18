# Database Migration Checklist

Use this checklist when creating or modifying database migrations.

## Before Creating Migration

- [ ] All model changes are complete and tested
- [ ] Environment is activated (venv)
- [ ] Database connection is working
- [ ] All new models are imported in `migrations/env.py`
- [ ] Ran `python validate_migrations.py` successfully

## Creating the Migration

- [ ] Used descriptive migration message
  ```bash
  python migrate.py create "add email column to users table"
  ```
- [ ] Reviewed auto-generated migration file in `migrations/versions/`
- [ ] Verified column types match model definitions
- [ ] Checked for data migrations needed
- [ ] Added proper downgrade logic

## Migration File Review

### Schema Changes
- [ ] All table creates/drops are present
- [ ] All column adds/drops/modifications are correct
- [ ] Indexes are created where needed
- [ ] Foreign keys are properly defined
- [ ] Unique constraints are added
- [ ] Check constraints are included (if any)

### Data Migrations
- [ ] Default values are set for new NOT NULL columns
- [ ] Data transformations are included
- [ ] Batch operations for large tables
- [ ] Proper error handling for data migrations

### Downgrade Function
- [ ] Reverse of all upgrade operations
- [ ] Data preservation logic (if needed)
- [ ] Foreign key dependencies handled in correct order
- [ ] Tested downgrade path

## Testing

### Local Testing
- [ ] Created test database (or backup existing)
- [ ] Applied migration: `python migrate.py upgrade`
- [ ] Verified tables/columns created correctly
- [ ] Tested application with new schema
- [ ] Rolled back: `python migrate.py downgrade`
- [ ] Re-applied: `python migrate.py upgrade`
- [ ] No errors in any step

### Pre-Commit Checks
- [ ] Ran `python scripts/check_migrations.py`
- [ ] All syntax checks passed
- [ ] No sensitive data in migration files
- [ ] Migration message is clear and descriptive

### Database Verification
```sql
-- Check table structure
\d table_name

-- Check indexes
\di

-- Check constraints
\d+ table_name

-- Verify data
SELECT COUNT(*) FROM table_name;
```

## Production Considerations

- [ ] Estimated migration execution time documented
- [ ] Large table migrations optimized (batching, indexes)
- [ ] Backward compatibility maintained (if needed)
- [ ] Rollback plan documented
- [ ] Team notified of migration
- [ ] Maintenance window scheduled (if needed)

## Zero-Downtime Migration Checklist

For production systems with uptime requirements:

### Phase 1: Additive Changes
- [ ] New columns added as NULL or with defaults
- [ ] New tables created
- [ ] New indexes created CONCURRENTLY (PostgreSQL)
- [ ] Application still works with old schema

### Phase 2: Data Migration
- [ ] Background job to populate new columns
- [ ] Progress monitoring in place
- [ ] Can be paused/resumed safely
- [ ] Old and new columns stay in sync

### Phase 3: Application Deployment
- [ ] Application updated to use new schema
- [ ] Gradual rollout (canary/blue-green)
- [ ] Monitoring for errors
- [ ] Easy rollback available

### Phase 4: Cleanup
- [ ] Old columns/tables dropped
- [ ] Constraints tightened (NULL → NOT NULL)
- [ ] Unused indexes removed
- [ ] Final verification

## Common Patterns

### Adding NOT NULL Column
```python
def upgrade():
    # 1. Add as nullable
    op.add_column('users', sa.Column('email', sa.String(255), nullable=True))
    
    # 2. Populate data
    op.execute("UPDATE users SET email = username || '@example.com' WHERE email IS NULL")
    
    # 3. Make NOT NULL
    op.alter_column('users', 'email', nullable=False)

def downgrade():
    op.drop_column('users', 'email')
```

### Renaming Column
```python
def upgrade():
    op.alter_column('users', 'old_name', new_column_name='new_name')

def downgrade():
    op.alter_column('users', 'new_name', new_column_name='old_name')
```

### Adding Foreign Key
```python
def upgrade():
    op.create_foreign_key(
        'fk_users_tenant',
        'users', 'tenants',
        ['tenant_id'], ['tenant_id'],
        ondelete='CASCADE'
    )

def downgrade():
    op.drop_constraint('fk_users_tenant', 'users', type_='foreignkey')
```

### Creating Index
```python
def upgrade():
    op.create_index('idx_users_email', 'users', ['email'])

def downgrade():
    op.drop_index('idx_users_email', 'users')
```

## Troubleshooting

### Migration Fails
1. Check database logs
2. Verify database connection
3. Check for locking issues
4. Review migration SQL
5. Test in isolated environment

### Can't Downgrade
1. Check if downgrade logic is complete
2. Verify foreign key dependencies
3. Check for data that would be lost
4. May need manual intervention

### Conflicts with Other Branches
1. Merge branch with migrations first
2. Create merge migration if needed
3. Run `alembic heads` to see multiple heads
4. Use `alembic merge` if necessary

## Documentation

After migration is complete:

- [ ] Updated CHANGELOG.md
- [ ] Documented schema changes
- [ ] Updated API documentation (if affected)
- [ ] Added migration notes to release notes
- [ ] Updated ERD (Entity Relationship Diagram) if maintained

## Sign-off

- [ ] Developer tested _______________
- [ ] Code reviewed by _______________
- [ ] Database reviewed by _______________
- [ ] Ready for deployment _______________

---

**Migration File**: `___________________________`
**Target Environment**: `___________________________`
**Estimated Duration**: `___________________________`
**Risk Level**: ⬜ Low  ⬜ Medium  ⬜ High
**Requires Downtime**: ⬜ Yes  ⬜ No

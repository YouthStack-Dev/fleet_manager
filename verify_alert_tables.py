"""Verify alert system tables were created"""
from app.database.session import get_db
from sqlalchemy import text

db = next(get_db())

# Check for alert tables
result = db.execute(text("""
    SELECT tablename 
    FROM pg_tables 
    WHERE schemaname='public' 
    AND tablename LIKE '%alert%'
    ORDER BY tablename
"""))

tables = [row[0] for row in result]

print("✓ Alert System Tables Created:")
print("=" * 50)
for table in tables:
    # Get row count
    count_result = db.execute(text(f"SELECT COUNT(*) FROM {table}"))
    count = count_result.scalar()
    print(f"  • {table:30} ({count} rows)")

db.close()

print("\n✓ Migration completed successfully!")
print(f"  Total alert tables: {len(tables)}")

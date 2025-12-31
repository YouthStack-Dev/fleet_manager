"""Verify alert system indexes were created"""
from app.database.session import get_db
from sqlalchemy import text

db = next(get_db())

# Check for alert indexes
result = db.execute(text("""
    SELECT 
        tablename,
        indexname,
        indexdef
    FROM pg_indexes
    WHERE schemaname = 'public' 
    AND tablename LIKE '%alert%'
    ORDER BY tablename, indexname
"""))

indexes = list(result)

print("✓ Alert System Indexes:")
print("=" * 80)

current_table = None
for table, index_name, index_def in indexes:
    if table != current_table:
        print(f"\n{table}:")
        current_table = table
    print(f"  • {index_name}")

db.close()

print(f"\n✓ Total indexes created: {len(indexes)}")

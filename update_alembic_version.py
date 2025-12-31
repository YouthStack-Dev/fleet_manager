"""Update alembic version to match migration files"""
from app.database.session import get_db
from sqlalchemy import text

db = next(get_db())

# Check current version
result = db.execute(text("SELECT version_num FROM alembic_version"))
current = result.fetchone()
print(f"Current version: {current[0] if current else 'None'}")

# Update to match migration files
db.execute(text("UPDATE alembic_version SET version_num = 'b75d731987dd'"))
db.commit()

# Verify update
result = db.execute(text("SELECT version_num FROM alembic_version"))
new = result.fetchone()
print(f"Updated version: {new[0]}")

db.close()
print("✓ Successfully updated alembic_version")

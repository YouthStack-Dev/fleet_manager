from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.tenant import Tenant
from app.seed.seed_data import seed_tenants

router = APIRouter(prefix="/seed",
    tags=["Seeding"])

@router.post("/seed")
def seed_database(
    force: bool = Query(False, description="Force reseed (delete + insert)"),
    db: Session = Depends(get_db),
):
    try:
        if force:
            # Wipe tenants before reseed
            db.query(Tenant).delete()
            db.commit()

        seed_tenants(db)

        return {"message": "Database seeded successfully."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Seeding failed: {str(e)}"
        )

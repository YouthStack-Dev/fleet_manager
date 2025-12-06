from sqlalchemy.orm import Session
from app.models.escort import Escort
from app.schemas.escort import EscortCreate, EscortUpdate
from typing import List, Optional


def get_escorts(db: Session, tenant_id: str, skip: int = 0, limit: int = 100) -> List[Escort]:
    return db.query(Escort).filter(Escort.tenant_id == tenant_id).offset(skip).limit(limit).all()


def get_escort(db: Session, escort_id: int, tenant_id: str) -> Optional[Escort]:
    return db.query(Escort).filter(
        Escort.escort_id == escort_id,
        Escort.tenant_id == tenant_id
    ).first()


def get_escort_by_phone(db: Session, phone: str, tenant_id: str) -> Optional[Escort]:
    return db.query(Escort).filter(
        Escort.phone == phone,
        Escort.tenant_id == tenant_id
    ).first()


def create_escort(db: Session, escort: EscortCreate, tenant_id: str) -> Escort:
    db_escort = Escort(
        tenant_id=tenant_id,
        vendor_id=escort.vendor_id,
        name=escort.name,
        phone=escort.phone,
        email=escort.email,
        address=escort.address,
        gender=escort.gender,
        is_active=escort.is_active,
        is_available=escort.is_available,
    )
    db.add(db_escort)
    db.commit()
    db.refresh(db_escort)
    return db_escort


def update_escort(db: Session, escort_id: int, escort_update: EscortUpdate, tenant_id: str) -> Optional[Escort]:
    db_escort = db.query(Escort).filter(
        Escort.escort_id == escort_id,
        Escort.tenant_id == tenant_id
    ).first()

    if db_escort:
        update_data = escort_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_escort, field, value)

        db.commit()
        db.refresh(db_escort)

    return db_escort


def delete_escort(db: Session, escort_id: int, tenant_id: str) -> bool:
    db_escort = db.query(Escort).filter(
        Escort.escort_id == escort_id,
        Escort.tenant_id == tenant_id
    ).first()

    if db_escort:
        db.delete(db_escort)
        db.commit()
        return True

    return False


def get_available_escorts(db: Session, tenant_id: str) -> List[Escort]:
    """Get escorts that are active and available for assignment"""
    return db.query(Escort).filter(
        Escort.tenant_id == tenant_id,
        Escort.is_active == True,
        Escort.is_available == True
    ).all()
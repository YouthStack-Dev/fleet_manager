from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional, List
from database.session import get_db
from app.models.driver import Driver
from app.schemas.driver import DriverCreate, DriverUpdate, DriverResponse, DriverPaginationResponse
from app.utils.auth import get_password_hash
from app.utils.pagination import paginate_query

router = APIRouter(prefix="/drivers", tags=["drivers"])

@router.post("/", response_model=DriverResponse, status_code=status.HTTP_201_CREATED)
def create_driver(driver: DriverCreate, db: Session = Depends(get_db)):
    db_driver = Driver(
        **driver.dict(exclude={"password"}),
        password=get_password_hash(driver.password)
    )
    db.add(db_driver)
    db.commit()
    db.refresh(db_driver)
    return db_driver

@router.get("/", response_model=DriverPaginationResponse)
def read_drivers(
    skip: int = 0,
    limit: int = 100,
    name: Optional[str] = None,
    vendor_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Driver)
    
    # Apply filters
    if name:
        query = query.filter(Driver.name.ilike(f"%{name}%"))
    if vendor_id:
        query = query.filter(Driver.vendor_id == vendor_id)
    if is_active is not None:
        query = query.filter(Driver.is_active == is_active)
    
    total, items = paginate_query(query, skip, limit)
    return {"total": total, "items": items}

@router.get("/{driver_id}", response_model=DriverResponse)
def read_driver(driver_id: int, db: Session = Depends(get_db)):
    db_driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
    if not db_driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Driver with ID {driver_id} not found"
        )
    return db_driver

@router.put("/{driver_id}", response_model=DriverResponse)
def update_driver(driver_id: int, driver_update: DriverUpdate, db: Session = Depends(get_db)):
    db_driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
    if not db_driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Driver with ID {driver_id} not found"
        )
    
    # Update only provided fields
    update_data = driver_update.dict(exclude_unset=True)
    
    # Hash password if it's being updated
    if "password" in update_data:
        update_data["password"] = get_password_hash(update_data["password"])
    
    for key, value in update_data.items():
        setattr(db_driver, key, value)
    
    db.commit()
    db.refresh(db_driver)
    return db_driver

@router.delete("/{driver_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_driver(driver_id: int, db: Session = Depends(get_db)):
    db_driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
    if not db_driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Driver with ID {driver_id} not found"
        )
    
    db.delete(db_driver)
    db.commit()
    return None

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from database.session import get_db
from app.models.vendor import Vendor
from app.schemas.vendor import VendorCreate, VendorUpdate, VendorResponse, VendorPaginationResponse
from app.utils.pagination import paginate_query

router = APIRouter(prefix="/vendors", tags=["vendors"])

@router.post("/", response_model=VendorResponse, status_code=status.HTTP_201_CREATED)
def create_vendor(vendor: VendorCreate, db: Session = Depends(get_db)):
    db_vendor = Vendor(**vendor.dict())
    db.add(db_vendor)
    db.commit()
    db.refresh(db_vendor)
    return db_vendor

@router.get("/", response_model=VendorPaginationResponse)
def read_vendors(
    skip: int = 0,
    limit: int = 100,
    name: Optional[str] = None,
    code: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Vendor)
    
    # Apply filters
    if name:
        query = query.filter(Vendor.name.ilike(f"%{name}%"))
    if code:
        query = query.filter(Vendor.code.ilike(f"%{code}%"))
    if is_active is not None:
        query = query.filter(Vendor.is_active == is_active)
    
    total, items = paginate_query(query, skip, limit)
    return {"total": total, "items": items}

@router.get("/{vendor_id}", response_model=VendorResponse)
def read_vendor(vendor_id: int, db: Session = Depends(get_db)):
    db_vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not db_vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with ID {vendor_id} not found"
        )
    return db_vendor

@router.put("/{vendor_id}", response_model=VendorResponse)
def update_vendor(vendor_id: int, vendor_update: VendorUpdate, db: Session = Depends(get_db)):
    db_vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not db_vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with ID {vendor_id} not found"
        )
    
    update_data = vendor_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_vendor, key, value)
    
    db.commit()
    db.refresh(db_vendor)
    return db_vendor

@router.delete("/{vendor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vendor(vendor_id: int, db: Session = Depends(get_db)):
    db_vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not db_vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with ID {vendor_id} not found"
        )
    
    db.delete(db_vendor)
    db.commit()
    return None

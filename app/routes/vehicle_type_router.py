from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.models.vehicle_type import VehicleType
from app.schemas.vehicle_type import VehicleTypeCreate, VehicleTypeUpdate, VehicleTypeResponse, VehicleTypePaginationResponse
from app.utils.pagination import paginate_query
from common_utils.auth.permission_checker import PermissionChecker

router = APIRouter(prefix="/vehicle-types", tags=["vehicle types"])

@router.post("/", response_model=VehicleTypeResponse, status_code=status.HTTP_201_CREATED)
def create_vehicle_type(
    vehicle_type: VehicleTypeCreate, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle-type.create"], check_tenant=True))
):
    db_vehicle_type = VehicleType(**vehicle_type.dict())
    db.add(db_vehicle_type)
    db.commit()
    db.refresh(db_vehicle_type)
    return db_vehicle_type

@router.get("/", response_model=VehicleTypePaginationResponse)
def read_vehicle_types(
    skip: int = 0,
    limit: int = 100,
    name: Optional[str] = None,
    vendor_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle-type.read"], check_tenant=True))
):
    query = db.query(VehicleType)
    
    # Apply filters
    if name:
        query = query.filter(VehicleType.name.ilike(f"%{name}%"))
    if vendor_id:
        query = query.filter(VehicleType.vendor_id == vendor_id)
    if is_active is not None:
        query = query.filter(VehicleType.is_active == is_active)
    
    total, items = paginate_query(query, skip, limit)
    return {"total": total, "items": items}

@router.get("/{vehicle_type_id}", response_model=VehicleTypeResponse)
def read_vehicle_type(
    vehicle_type_id: int, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle-type.read"], check_tenant=True))
):
    db_vehicle_type = db.query(VehicleType).filter(VehicleType.vehicle_type_id == vehicle_type_id).first()
    if not db_vehicle_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle Type with ID {vehicle_type_id} not found"
        )
    return db_vehicle_type

@router.put("/{vehicle_type_id}", response_model=VehicleTypeResponse)
def update_vehicle_type(
    vehicle_type_id: int, 
    vehicle_type_update: VehicleTypeUpdate, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle-type.update"], check_tenant=True))
):
    db_vehicle_type = db.query(VehicleType).filter(VehicleType.vehicle_type_id == vehicle_type_id).first()
    if not db_vehicle_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle Type with ID {vehicle_type_id} not found"
        )
    
    update_data = vehicle_type_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_vehicle_type, key, value)
    
    db.commit()
    db.refresh(db_vehicle_type)
    return db_vehicle_type

@router.delete("/{vehicle_type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle_type(
    vehicle_type_id: int, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle-type.delete"], check_tenant=True))
):
    db_vehicle_type = db.query(VehicleType).filter(VehicleType.vehicle_type_id == vehicle_type_id).first()
    if not db_vehicle_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle Type with ID {vehicle_type_id} not found"
        )
    
    db.delete(db_vehicle_type)
    db.commit()
    return None

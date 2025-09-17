from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleCreate, VehicleUpdate, VehicleResponse, VehiclePaginationResponse
from app.utils.pagination import paginate_query
from common_utils.auth.permission_checker import PermissionChecker

router = APIRouter(prefix="/vehicles", tags=["vehicles"])

@router.post("/", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
def create_vehicle(
    vehicle: VehicleCreate, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle.create"], check_tenant=True))
):
    db_vehicle = Vehicle(**vehicle.dict())
    db.add(db_vehicle)
    db.commit()
    db.refresh(db_vehicle)
    return db_vehicle

@router.get("/", response_model=VehiclePaginationResponse)
def read_vehicles(
    skip: int = 0,
    limit: int = 100,
    rc_number: Optional[str] = None,
    vendor_id: Optional[int] = None,
    vehicle_type_id: Optional[int] = None,
    driver_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle.read"], check_tenant=True))
):
    query = db.query(Vehicle)
    
    # Apply filters
    if rc_number:
        query = query.filter(Vehicle.rc_number.ilike(f"%{rc_number}%"))
    if vendor_id:
        query = query.filter(Vehicle.vendor_id == vendor_id)
    if vehicle_type_id:
        query = query.filter(Vehicle.vehicle_type_id == vehicle_type_id)
    if driver_id:
        query = query.filter(Vehicle.driver_id == driver_id)
    if is_active is not None:
        query = query.filter(Vehicle.is_active == is_active)
    
    total, items = paginate_query(query, skip, limit)
    return {"total": total, "items": items}

@router.get("/{vehicle_id}", response_model=VehicleResponse)
def read_vehicle(
    vehicle_id: int, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle.read"], check_tenant=True))
):
    db_vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == vehicle_id).first()
    if not db_vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle with ID {vehicle_id} not found"
        )
    return db_vehicle

@router.put("/{vehicle_id}", response_model=VehicleResponse)
def update_vehicle(
    vehicle_id: int, 
    vehicle_update: VehicleUpdate, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle.update"], check_tenant=True))
):
    db_vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == vehicle_id).first()
    if not db_vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle with ID {vehicle_id} not found"
        )
    
    update_data = vehicle_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_vehicle, key, value)
    
    db.commit()
    db.refresh(db_vehicle)
    return db_vehicle

@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(
    vehicle_id: int, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vehicle.delete"], check_tenant=True))
):
    db_vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == vehicle_id).first()
    if not db_vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle with ID {vehicle_id} not found"
        )
    
    db.delete(db_vehicle)
    db.commit()
    return None

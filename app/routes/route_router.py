from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database.session import get_db
from app.models.route import Route
from app.schemas.route import RouteCreate, RouteUpdate, RouteResponse, RoutePaginationResponse, RouteStatusEnum
from app.utils.pagination import paginate_query
from common_utils.auth.permission_checker import PermissionChecker

router = APIRouter(prefix="/routes", tags=["routes"])

@router.post("/", response_model=RouteResponse, status_code=status.HTTP_201_CREATED)
def create_route(
    route: RouteCreate, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.create"], check_tenant=True))
):
    db_route = Route(**route.dict())
    db.add(db_route)
    db.commit()
    db.refresh(db_route)
    return db_route

@router.get("/", response_model=RoutePaginationResponse)
def read_routes(
    skip: int = 0,
    limit: int = 100,
    route_code: Optional[str] = None,
    shift_id: Optional[int] = None,
    status: Optional[RouteStatusEnum] = None,
    assigned_vendor_id: Optional[int] = None,
    assigned_driver_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.read"], check_tenant=True))
):
    query = db.query(Route)
    
    # Apply filters
    if route_code:
        query = query.filter(Route.route_code.ilike(f"%{route_code}%"))
    if shift_id:
        query = query.filter(Route.shift_id == shift_id)
    if status:
        query = query.filter(Route.status == status)
    if assigned_vendor_id:
        query = query.filter(Route.assigned_vendor_id == assigned_vendor_id)
    if assigned_driver_id:
        query = query.filter(Route.assigned_driver_id == assigned_driver_id)
    if is_active is not None:
        query = query.filter(Route.is_active == is_active)
    
    total, items = paginate_query(query, skip, limit)
    return {"total": total, "items": items}

@router.get("/{route_id}", response_model=RouteResponse)
def read_route(
    route_id: int, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.read"], check_tenant=True))
):
    db_route = db.query(Route).filter(Route.route_id == route_id).first()
    if not db_route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route with ID {route_id} not found"
        )
    return db_route

@router.put("/{route_id}", response_model=RouteResponse)
def update_route(
    route_id: int, 
    route_update: RouteUpdate, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.update"], check_tenant=True))
):
    db_route = db.query(Route).filter(Route.route_id == route_id).first()
    if not db_route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route with ID {route_id} not found"
        )
    
    update_data = route_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_route, key, value)
    
    db.commit()
    db.refresh(db_route)
    return db_route

@router.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_route(
    route_id: int, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["route.delete"], check_tenant=True))
):
    db_route = db.query(Route).filter(Route.route_id == route_id).first()
    if not db_route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route with ID {route_id} not found"
        )
    
    db.delete(db_route)
    db.commit()
    return None

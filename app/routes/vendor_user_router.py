from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.models.vendor_user import VendorUser
from app.schemas.vendor_user import VendorUserCreate, VendorUserUpdate, VendorUserResponse, VendorUserPaginationResponse
from app.utils.pagination import paginate_query
from app.models.vendor import Vendor
from common_utils.auth.permission_checker import PermissionChecker

router = APIRouter(prefix="/vendor-users", tags=["vendor users"])

@router.post("/", response_model=VendorUserResponse, status_code=status.HTTP_201_CREATED)
def create_vendor_user(
    vendor_user: VendorUserCreate, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor-user.create"], check_tenant=True))
):
    db_vendor_user = VendorUser(
        **vendor_user.dict(exclude={"password"}),
        password=vendor_user.password
    )
    db.add(db_vendor_user)
    db.commit()
    db.refresh(db_vendor_user)
    # Convert the model to a schema before returning to ensure all fields match
    return VendorUserResponse.from_orm(db_vendor_user)

@router.get("/", response_model=VendorUserPaginationResponse)
def read_vendor_users(
    skip: int = 0,
    limit: int = 100,
    name: Optional[str] = None,
    email: Optional[str] = None,
    vendor_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor-user.read"], check_tenant=True))
):
    query = db.query(VendorUser)
    
    # Apply filters
    if name:
        query = query.filter(VendorUser.name.ilike(f"%{name}%"))
    if email:
        query = query.filter(VendorUser.email.ilike(f"%{email}%"))
    if vendor_id:
        query = query.filter(VendorUser.vendor_id == vendor_id)
    if is_active is not None:
        query = query.filter(VendorUser.is_active == is_active)
    
    total, items = paginate_query(query, skip, limit)
    # Ensure items are properly converted to response schema
    items = [VendorUserResponse.from_orm(item) for item in items]
    return {"total": total, "items": items}

@router.get("/{vendor_user_id}", response_model=VendorUserResponse)
def read_vendor_user(
    vendor_user_id: int, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor-user.read"], check_tenant=True))
):
    db_vendor_user = db.query(VendorUser).filter(VendorUser.vendor_user_id == vendor_user_id).first()
    if not db_vendor_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor User with ID {vendor_user_id} not found"
        )
    return VendorUserResponse.from_orm(db_vendor_user)

@router.put("/{vendor_user_id}", response_model=VendorUserResponse)
def update_vendor_user(
    vendor_user_id: int, 
    vendor_user_update: VendorUserUpdate, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor-user.update"], check_tenant=True))
):
    db_vendor_user = db.query(VendorUser).filter(VendorUser.vendor_user_id == vendor_user_id).first()
    if not db_vendor_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor User with ID {vendor_user_id} not found"
        )
    
    update_data = vendor_user_update.dict(exclude_unset=True)
    
    # Check if vendor_id is being updated and if it exists
    if "vendor_id" in update_data:
        vendor_exists = db.query(Vendor).filter(Vendor.vendor_id == update_data["vendor_id"]).first()
        if not vendor_exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Vendor with ID {update_data['vendor_id']} does not exist"
            )
    
    # Hash password if it's being updated
    if "password" in update_data:
        update_data["password"] = update_data["password"]
    
    for key, value in update_data.items():
        setattr(db_vendor_user, key, value)
    
    try:
        db.commit()
        db.refresh(db_vendor_user)
        return VendorUserResponse.from_orm(db_vendor_user)
    except Exception as e:
        db.rollback()
        # Log the error here if needed
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update vendor user. Please check your input data."
        )

@router.delete("/{vendor_user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vendor_user(
    vendor_user_id: int, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor-user.delete"], check_tenant=True))
):
    db_vendor_user = db.query(VendorUser).filter(VendorUser.vendor_user_id == vendor_user_id).first()
    if not db_vendor_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor User with ID {vendor_user_id} not found"
        )
    
    db.delete(db_vendor_user)
    db.commit()
    return None

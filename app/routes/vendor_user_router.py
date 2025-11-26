from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional
from app.database.session import get_db
from app.models.vendor_user import VendorUser
from app.models.vendor import Vendor
from app.schemas.vendor_user import VendorUserCreate, VendorUserUpdate, VendorUserResponse, VendorUserPaginationResponse
from app.utils.pagination import paginate_query
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from app.utils.audit_helper import log_audit
from app.crud.vendor_user import vendor_user_crud
from app.crud.vendor import vendor_crud
from common_utils.auth.permission_checker import PermissionChecker
from common_utils.auth.utils import hash_password
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/vendor-users", tags=["vendor users"])

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_vendor_user(
    vendor_user: VendorUserCreate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor-user.create"], check_tenant=True))
):
    """
    Create a new vendor user.
    
    Rules:
    - Validates vendor exists and belongs to the tenant
    - Checks for duplicate email/phone within tenant
    - Hashes password before storing
    - Creates audit log
    """
    try:
        tenant_id = user_data.get("tenant_id")
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Tenant ID is required",
                    error_code="TENANT_ID_REQUIRED"
                )
            )

        # Validate vendor exists and belongs to tenant
        vendor = vendor_crud.get(db, id=vendor_user.vendor_id)
        if not vendor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vendor with ID {vendor_user.vendor_id} not found",
                    error_code="VENDOR_NOT_FOUND"
                )
            )
        
        if vendor.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message=f"Vendor does not belong to your tenant",
                    error_code="VENDOR_TENANT_MISMATCH"
                )
            )

        # Check for duplicate email within tenant
        existing_email = db.query(VendorUser).filter(
            VendorUser.tenant_id == tenant_id,
            VendorUser.email == vendor_user.email
        ).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message=f"Email '{vendor_user.email}' already exists in this tenant",
                    error_code="DUPLICATE_EMAIL"
                )
            )

        # Check for duplicate phone within tenant
        existing_phone = db.query(VendorUser).filter(
            VendorUser.tenant_id == tenant_id,
            VendorUser.phone == vendor_user.phone
        ).first()
        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message=f"Phone '{vendor_user.phone}' already exists in this tenant",
                    error_code="DUPLICATE_PHONE"
                )
            )

        # Create vendor user with hashed password
        db_vendor_user = VendorUser(
            tenant_id=tenant_id,
            vendor_id=vendor_user.vendor_id,
            name=vendor_user.name,
            email=vendor_user.email,
            phone=vendor_user.phone,
            password=hash_password(vendor_user.password),
            role_id=vendor_user.role_id,
            is_active=vendor_user.is_active
        )
        db.add(db_vendor_user)
        db.commit()
        db.refresh(db_vendor_user)

        # 🔍 Audit Log: Vendor User Creation
        try:
            vendor_user_data = {
                "vendor_user_id": db_vendor_user.vendor_user_id,
                "name": db_vendor_user.name,
                "email": db_vendor_user.email,
                "phone": db_vendor_user.phone,
                "vendor_id": db_vendor_user.vendor_id,
                "role_id": db_vendor_user.role_id,
                "is_active": db_vendor_user.is_active
            }
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="vendor_user",
                action="CREATE",
                user_data=user_data,
                description=f"Created vendor user '{db_vendor_user.name}' ({db_vendor_user.email}) for vendor {vendor_user.vendor_id}",
                new_values=vendor_user_data,
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for vendor user creation: {str(audit_error)}")

        logger.info(
            f"Vendor user created successfully: vendor_user_id={db_vendor_user.vendor_user_id}, "
            f"name={db_vendor_user.name}, vendor_id={vendor_user.vendor_id}"
        )

        return ResponseWrapper.success(
            data=VendorUserResponse.model_validate(db_vendor_user, from_attributes=True),
            message="Vendor user created successfully"
        )

    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while creating vendor user: {e}")
        raise handle_http_error(e)

@router.get("/")
def read_vendor_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    name: Optional[str] = None,
    email: Optional[str] = None,
    vendor_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor-user.read"], check_tenant=True))
):
    """
    Get all vendor users with pagination and filtering.
    
    Filters:
    - name: Search by name (case-insensitive partial match)
    - email: Search by email (case-insensitive partial match)
    - vendor_id: Filter by vendor
    - is_active: Filter by active status
    """
    try:
        tenant_id = user_data.get("tenant_id")
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Tenant ID is required",
                    error_code="TENANT_ID_REQUIRED"
                )
            )

        query = db.query(VendorUser).filter(VendorUser.tenant_id == tenant_id)
        
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
        
        logger.debug(
            f"Retrieved {len(items)} vendor users out of {total} total for tenant {tenant_id}"
        )

        return ResponseWrapper.success(
            data={
                "total": total,
                "items": [VendorUserResponse.model_validate(item, from_attributes=True) for item in items]
            },
            message=f"Retrieved {len(items)} vendor user(s)"
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except Exception as e:
        logger.exception(f"Unexpected error while fetching vendor users: {e}")
        raise handle_http_error(e)

@router.get("/{vendor_user_id}")
def read_vendor_user(
    vendor_user_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor-user.read"], check_tenant=True))
):
    """
    Get a specific vendor user by ID.
    
    Validates:
    - Vendor user exists
    - Vendor user belongs to the requester's tenant
    """
    try:
        tenant_id = user_data.get("tenant_id")
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Tenant ID is required",
                    error_code="TENANT_ID_REQUIRED"
                )
            )

        db_vendor_user = db.query(VendorUser).filter(
            VendorUser.vendor_user_id == vendor_user_id,
            VendorUser.tenant_id == tenant_id
        ).first()

        if not db_vendor_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vendor user with ID {vendor_user_id} not found",
                    error_code="VENDOR_USER_NOT_FOUND"
                )
            )

        logger.debug(f"Retrieved vendor user: {vendor_user_id}")

        return ResponseWrapper.success(
            data=VendorUserResponse.model_validate(db_vendor_user, from_attributes=True),
            message="Vendor user retrieved successfully"
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except Exception as e:
        logger.exception(f"Unexpected error while fetching vendor user {vendor_user_id}: {e}")
        raise handle_http_error(e)

@router.put("/{vendor_user_id}")
def update_vendor_user(
    vendor_user_id: int,
    vendor_user_update: VendorUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor-user.update"], check_tenant=True))
):
    """
    Update a vendor user.
    
    Validates:
    - Vendor user exists and belongs to tenant
    - Vendor exists (if vendor_id is being updated)
    - No duplicate email/phone within tenant
    - Hashes password if updated
    - Creates audit log
    """
    try:
        tenant_id = user_data.get("tenant_id")
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Tenant ID is required",
                    error_code="TENANT_ID_REQUIRED"
                )
            )

        # Fetch existing vendor user
        db_vendor_user = db.query(VendorUser).filter(
            VendorUser.vendor_user_id == vendor_user_id,
            VendorUser.tenant_id == tenant_id
        ).first()

        if not db_vendor_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vendor user with ID {vendor_user_id} not found",
                    error_code="VENDOR_USER_NOT_FOUND"
                )
            )

        # Capture old values for audit
        old_values = {
            "name": db_vendor_user.name,
            "email": db_vendor_user.email,
            "phone": db_vendor_user.phone,
            "vendor_id": db_vendor_user.vendor_id,
            "is_active": db_vendor_user.is_active
        }

        update_data = vendor_user_update.dict(exclude_unset=True)

        # Check if vendor_id is being updated and validate it
        if "vendor_id" in update_data and update_data["vendor_id"] != db_vendor_user.vendor_id:
            vendor = vendor_crud.get(db, id=update_data["vendor_id"])
            if not vendor:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        message=f"Vendor with ID {update_data['vendor_id']} not found",
                        error_code="VENDOR_NOT_FOUND"
                    )
                )
            if vendor.tenant_id != tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Vendor does not belong to your tenant",
                        error_code="VENDOR_TENANT_MISMATCH"
                    )
                )

        # Check for duplicate email
        if "email" in update_data and update_data["email"] != db_vendor_user.email:
            existing_email = db.query(VendorUser).filter(
                VendorUser.tenant_id == tenant_id,
                VendorUser.email == update_data["email"],
                VendorUser.vendor_user_id != vendor_user_id
            ).first()
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message=f"Email '{update_data['email']}' already exists in this tenant",
                        error_code="DUPLICATE_EMAIL"
                    )
                )

        # Check for duplicate phone
        if "phone" in update_data and update_data["phone"] != db_vendor_user.phone:
            existing_phone = db.query(VendorUser).filter(
                VendorUser.tenant_id == tenant_id,
                VendorUser.phone == update_data["phone"],
                VendorUser.vendor_user_id != vendor_user_id
            ).first()
            if existing_phone:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message=f"Phone '{update_data['phone']}' already exists in this tenant",
                        error_code="DUPLICATE_PHONE"
                    )
                )

        # Hash password if being updated
        if "password" in update_data and update_data["password"]:
            update_data["password"] = hash_password(update_data["password"])

        # Apply updates
        for key, value in update_data.items():
            setattr(db_vendor_user, key, value)

        db.commit()
        db.refresh(db_vendor_user)

        # Capture new values for audit
        new_values = {
            "name": db_vendor_user.name,
            "email": db_vendor_user.email,
            "phone": db_vendor_user.phone,
            "vendor_id": db_vendor_user.vendor_id,
            "is_active": db_vendor_user.is_active
        }

        # 🔍 Audit Log: Vendor User Update
        try:
            changed_fields = {k: {"old": old_values[k], "new": new_values[k]} 
                            for k in old_values if old_values[k] != new_values[k]}
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="vendor_user",
                action="UPDATE",
                user_data=user_data,
                description=f"Updated vendor user '{db_vendor_user.name}' (ID: {vendor_user_id})",
                new_values={"changed_fields": changed_fields, "new_state": new_values},
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for vendor user update: {str(audit_error)}")

        logger.info(
            f"Vendor user updated successfully: vendor_user_id={vendor_user_id}, "
            f"name={db_vendor_user.name}"
        )

        return ResponseWrapper.success(
            data=VendorUserResponse.model_validate(db_vendor_user, from_attributes=True),
            message="Vendor user updated successfully"
        )

    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while updating vendor user {vendor_user_id}: {e}")
        raise handle_http_error(e)

@router.patch("/{vendor_user_id}/toggle-status")
def toggle_vendor_user_status(
    vendor_user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor-user.update"], check_tenant=True))
):
    """
    Toggle vendor user active status.
    
    Validates:
    - Vendor user exists and belongs to tenant
    - Creates audit log for status change
    """
    try:
        tenant_id = user_data.get("tenant_id")
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Tenant ID is required",
                    error_code="TENANT_ID_REQUIRED"
                )
            )

        # Fetch vendor user
        db_vendor_user = db.query(VendorUser).filter(
            VendorUser.vendor_user_id == vendor_user_id,
            VendorUser.tenant_id == tenant_id
        ).first()

        if not db_vendor_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vendor user with ID {vendor_user_id} not found",
                    error_code="VENDOR_USER_NOT_FOUND"
                )
            )

        # Capture old status
        old_status = db_vendor_user.is_active

        # Toggle status
        db_vendor_user.is_active = not db_vendor_user.is_active
        db.commit()
        db.refresh(db_vendor_user)

        # 🔍 Audit Log: Status Toggle
        try:
            status_text = 'active' if db_vendor_user.is_active else 'inactive'
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="vendor_user",
                action="UPDATE",
                user_data=user_data,
                description=f"Toggled vendor user '{db_vendor_user.name}' status to {status_text}",
                new_values={"old_status": old_status, "new_status": db_vendor_user.is_active},
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for status toggle: {str(audit_error)}")

        logger.info(
            f"Toggled vendor user {vendor_user_id} status to "
            f"{'active' if db_vendor_user.is_active else 'inactive'}"
        )

        return ResponseWrapper.success(
            data=VendorUserResponse.model_validate(db_vendor_user, from_attributes=True),
            message=f"Vendor user is now {'active' if db_vendor_user.is_active else 'inactive'}"
        )

    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while toggling vendor user {vendor_user_id} status: {e}")
        raise handle_http_error(e)

@router.delete("/{vendor_user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vendor_user(
    vendor_user_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor-user.delete"], check_tenant=True))
):
    """
    Delete a vendor user by ID.
    
    Note: This is a hard delete. Consider using toggle-status for soft delete instead.
    
    Validates:
    - Vendor user exists and belongs to tenant
    """
    try:
        tenant_id = user_data.get("tenant_id")
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Tenant ID is required",
                    error_code="TENANT_ID_REQUIRED"
                )
            )

        db_vendor_user = db.query(VendorUser).filter(
            VendorUser.vendor_user_id == vendor_user_id,
            VendorUser.tenant_id == tenant_id
        ).first()

        if not db_vendor_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vendor user with ID {vendor_user_id} not found",
                    error_code="VENDOR_USER_NOT_FOUND"
                )
            )

        db.delete(db_vendor_user)
        db.commit()

        logger.info(f"Vendor user deleted successfully: {vendor_user_id}")
        return None

    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while deleting vendor user {vendor_user_id}: {e}")
        raise handle_http_error(e)

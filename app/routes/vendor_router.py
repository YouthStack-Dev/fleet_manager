import json
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional
from app.database.session import get_db
from app.models.iam.role import Role
from app.models.vendor import Vendor
from app.models.vendor_user import VendorUser
from app.schemas.vendor import VendorCreate, VendorUpdate, VendorResponse, VendorPaginationResponse
from app.utils.pagination import paginate_query
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger
from app.crud.tenant import tenant_crud
from app.crud.vendor import vendor_crud
from common_utils.auth.utils import hash_password
from app.utils.audit_helper import log_audit

logger = get_logger(__name__)
router = APIRouter(prefix="/vendors", tags=["vendors"])
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_vendor(
    vendor: VendorCreate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor.create"], check_tenant=False)),
):
    """
    Create a new vendor.

    Only Admin and Employee users can create vendors.
    The vendor object must include a tenant_id, which will be used to scope the vendor to a specific tenant.
    The vendor object may also include an admin_email and admin_phone, which will be used to create a default VendorAdmin user for the vendor.
    The vendor object may also include an admin_password, which will be used to set the password for the defaultVendorAdmin user. If not provided, the password will be set to "default@123".
    The API will return a response containing the created vendor object and the created defaultVendorAdmin user object.

    Raises:
        HTTPException: If the user is not authorized to create vendors, or if the user does not have a valid tenant_id.
        HTTPException: If the tenant_id is invalid or inactive.
        HTTPException: If the vendor object is missing required fields such as tenant_id, admin_email, admin_phone.
        HTTPException: If the vendor object is invalid, such as duplicate vendor_code or invalid email/phone.
        HTTPException: If an unexpected error occurs while creating the vendor.
    """
    try:
        logger.info(f"Create vendor request: {vendor.dict()}")
        logger.debug(f"User data from token: {user_data}")

        # --- Restrict by user_type ---
        if user_data.get("user_type") not in ["admin", "employee"]:
            logger.warning(
                f"Unauthorized vendor creation attempt by user_type={user_data.get('user_type')}, "
                f"user_id={user_data.get('user_id')}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Only Admin and Employee users can create vendors",
                    error_code="UNAUTHORIZED_USER_TYPE",
                ),
            )

        # --- Override tenant_id from token if present ---
        if user_data.get("tenant_id"):
            vendor.tenant_id = user_data["tenant_id"]

        logger.debug(f"Tenant ID resolved: {vendor.tenant_id}")

        if not vendor.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Tenant ID is required",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )

        # --- Validate tenant ---
        tenant = tenant_crud.get_by_id(db, tenant_id=vendor.tenant_id)
        if not tenant or not tenant.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Tenant '{vendor.tenant_id}' not found or inactive",
                    error_code="TENANT_NOT_FOUND",
                ),
            )

        # ================================
        # Transaction Start
        # ================================
        # --- Create Vendor ---
        db_vendor = vendor_crud.create(db, obj_in=vendor)
        db.flush()
        logger.info(f"Vendor created: {db_vendor.vendor_id}")

        # --- Get System VendorAdmin Role ---
        admin_role = db.query(Role).filter(
            Role.is_system_role == True,
            Role.name == "VendorAdmin"
        ).first()

        if not admin_role:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ResponseWrapper.error(
                    message="System role 'VendorAdmin' is missing. Please contact admin.",
                    error_code="SYSTEM_ROLE_MISSING",
                ),
            )

        # --- Validate admin details ---
        if not vendor.admin_email or not vendor.admin_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Admin email and phone are mandatory",
                    error_code="ADMIN_DETAILS_REQUIRED",
                ),
            )

        # --- Create Default VendorAdmin User ---
        default_password = vendor.admin_password or "default@123"
        vendor_user_in = VendorUser(
            tenant_id=vendor.tenant_id,   # ✅ always set
            vendor_id=db_vendor.vendor_id,
            name=vendor.admin_name or f"Admin_{db_vendor.vendor_id}",
            email=vendor.admin_email,
            phone=vendor.admin_phone,
            password=hash_password(default_password),
            role_id=admin_role.role_id,   # ✅ assign system VendorAdmin role
            is_active=True,
        )
        db.add(vendor_user_in)
        db.flush()
        logger.info(f"VendorAdmin user created: {vendor_user_in.email}")

        # --- Commit transaction ---
        db.commit()
        db.refresh(db_vendor)

        # 🔍 Audit Log: Vendor Creation
        try:
            vendor_data_for_audit = {
                "vendor_id": db_vendor.vendor_id,
                "name": db_vendor.name,
                "vendor_code": db_vendor.vendor_code,
                "email": db_vendor.email,
                "phone": db_vendor.phone,
                "tenant_id": db_vendor.tenant_id,
                "is_active": db_vendor.is_active
            }
            log_audit(
                db=db,
                tenant_id=db_vendor.tenant_id,
                module="vendor",
                action="CREATE",
                user_data=user_data,
                description=f"Created vendor '{db_vendor.name}' ({db_vendor.vendor_code})",
                new_values=vendor_data_for_audit,
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for vendor creation: {str(audit_error)}")

        logger.info(f"Vendor creation completed: {db_vendor.vendor_id}")

        return ResponseWrapper.success(
            data={
                "vendor": VendorResponse.model_validate(db_vendor, from_attributes=True),
                "vendor_admin": {
                    "vendor_user_id": vendor_user_in.vendor_user_id,
                    "name": vendor_user_in.name,
                    "email": vendor_user_in.email,
                    "phone": vendor_user_in.phone,
                    "role_id": vendor_user_in.role_id,
                },
            },
            message="Vendor and default admin user created successfully",
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while creating vendor: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Unexpected server error while creating vendor",
                error_code="INTERNAL_SERVER_ERROR",
                details={"error": str(e)},
            ),
        )

       

@router.get("/", status_code=status.HTTP_200_OK)
def read_vendors(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Max number of records to fetch"),
    name: Optional[str] = Query(None, description="Filter vendors by name"),
    code: Optional[str] = Query(None, description="Filter vendors by vendor_code"),
    is_active: Optional[bool] = Query(None, description="Filter vendors by active status"),
    tenant: Optional[str] = Query(None, description="Filter by tenant_id (SuperAdmin only)"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor.read"], check_tenant=True)),
):

    
    """
    Fetch a list of vendors with optional filters.

    Rules:
    - user_type == vendor/driver or missing → Forbidden
    - user_type == employee → can fetch only their tenant
    - other (admin) → can apply filters and fetch multiple vendors

    Args:
        skip (int): number of records to skip
        limit (int): max number of records to fetch
        name (Optional[str]): filter vendors by name
        code (Optional[str]): filter vendors by vendor_code
        is_active (Optional[bool]): filter vendors by active status
        tenant (Optional[str]): filter by tenant_id (Admin only)

    Returns:
        ResponseWrapper: a successful response with the list of vendors
    """
    try:
        user_type = user_data.get("user_type")
        tenant_id = user_data.get("tenant_id")
        vendor_id = user_data.get("vendor_id")

        # --- Restrict by user_type ---
        if user_type == "driver":
            logger.warning(f"Driver tried to access vendor list: user_id={user_data.get('user_id')}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Drivers are not allowed to fetch vendors",
                    error_code="FORBIDDEN_USER_TYPE",
                ),
            )

        # Vendor user → only their own vendor
        if user_type == "vendor":
            if not vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Vendor ID missing in token for vendor",
                        error_code="VENDOR_ID_REQUIRED",
                    ),
                )
            vendor = db.query(Vendor).filter(Vendor.vendor_id == int(vendor_id)).first()
            if not vendor:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        message=f"Vendor not found for vendor_id={vendor_id}",
                        error_code="VENDOR_NOT_FOUND",
                    ),
                )
            vendor_response = VendorResponse.model_validate(vendor, from_attributes=True)
            logger.info(f"Fetched vendor details for vendor_id={vendor_id}, user_type=vendor")

            # ✅ Return in pagination format for schema consistency
            return ResponseWrapper.success(
                data=VendorPaginationResponse(total=1, items=[vendor_response]),
                message="Vendor details fetched successfully",
            )

        # Employee → scoped by tenant
        query = db.query(Vendor)
        if user_type == "employee":
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
            query = query.filter(Vendor.tenant_id == tenant_id)

        # Admin → unrestricted
        elif user_type == "admin":
            logger.info("teant filter ignored for admin users")
            if tenant:
                query = query.filter(Vendor.tenant_id == tenant)

        # --- Apply other optional filters ---
        if name:
            query = query.filter(Vendor.name.ilike(f"%{name}%"))
        if code:
            query = query.filter(Vendor.vendor_code.ilike(f"%{code}%"))
        if is_active is not None:
            query = query.filter(Vendor.is_active == is_active)

        total, items = paginate_query(query, skip, limit)
        vendors = [VendorResponse.model_validate(v, from_attributes=True) for v in items]

        logger.info(
            f"Fetched {len(vendors)} vendors "
            f"(total={total}, user_type={user_type}, tenant={tenant_id or tenant or 'ALL'}, vendor={vendor_id or 'ALL'}, skip={skip}, limit={limit})"
        )
        return ResponseWrapper.success(
            data=VendorPaginationResponse(total=total, items=vendors),
            message="Vendors fetched successfully",
        )

    except SQLAlchemyError as e:
        # Handle DB errors in a structured way
        raise handle_db_error(e)
    except HTTPException:
        # Propagate known HTTPExceptions
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        logger.exception(f"Unexpected error while fetching vendors: {str(e)}")
        raise handle_http_error(e)



@router.get("/{vendor_id}", status_code=status.HTTP_200_OK)
def read_vendor(
    vendor_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor.read"], check_tenant=True))
):
    
    
    
    """
    Fetch a vendor by ID.

    Rules:
    - user_type == vendor/driver or missing → Forbidden
    - user_type == employee → can fetch only vendors in their tenant
    - other (admin) → can fetch any vendor

    Args:
        vendor_id (int): the ID of the vendor to fetch
        db (Session): the DB session
        user_data (dict): the user data from the token

    Returns:
        ResponseWrapper: a successful response with the vendor data
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")
        token_vendor_id = user_data.get("vendor_id")

        query = db.query(Vendor)

        # Vendor user → only their own vendor
        if user_type == "vendor":
            if not token_vendor_id or int(token_vendor_id) != vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Vendors can only access their own record",
                        error_code="FORBIDDEN_VENDOR_ACCESS"
                    )
                )
            query = query.filter(Vendor.vendor_id == vendor_id)

        # Employee → only vendors in their tenant
        elif user_type == "employee":
            if not token_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_REQUIRED"
                    )
                )
            query = query.filter(Vendor.vendor_id == vendor_id, Vendor.tenant_id == token_tenant_id)

        # Admin → unrestricted
        else:
            query = query.filter(Vendor.vendor_id == vendor_id)

        db_vendor = query.first()

        if not db_vendor:
            scope = token_tenant_id if token_tenant_id else "ALL"
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vendor with ID '{vendor_id}' not found in tenant '{scope}'",
                    error_code="VENDOR_NOT_FOUND"
                )
            )

        logger.info(f"Vendor fetched successfully: vendor_id={vendor_id}, scope={token_tenant_id or 'ALL'}")

        return ResponseWrapper.success(
            data=VendorResponse.model_validate(db_vendor, from_attributes=True),
            message="Vendor fetched successfully"
        )

    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while fetching vendor {vendor_id}: {e}")
        raise handle_http_error(e)



@router.put("/{vendor_id}", status_code=status.HTTP_200_OK)
def update_vendor(
    vendor_id: int,
    vendor_update: VendorUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor.update"], check_tenant=True))
):

    """
    Update a vendor by ID.

    Only Admin and Employee users can update vendors.
    The vendor object must include a tenant_id, which will be used to scope the vendor to a specific tenant.
    The vendor object may also include an admin_email and admin_phone, which will be used to create a default VendorAdmin user for the vendor.
    The vendor object may also include an admin_password, which will be used to set the password for the defaultVendorAdmin user. If not provided, the password will be set to "default@123".
    The API will return a response containing the updated vendor object and the created defaultVendorAdmin user object.

    Raises:
        HTTPException: If the user is not authorized to update vendors, or if the user does not have a valid tenant_id.
        HTTPException: If the vendor object is missing required fields such as tenant_id, admin_email, admin_phone.
        HTTPException: If the vendor object is invalid, such as duplicate vendor_code or invalid email/phone.
        HTTPException: If an unexpected error occurs while updating the vendor.
    """
    try:
        # First take from payload
        tenant_id = getattr(vendor_update, "tenant_id", None)
        logger.debug(f"Initial tenant_id from payload: {tenant_id}")

        # If tenant_id exists in token, overwrite payload
        token_tenant_id = user_data.get("tenant_id")
        logger.debug(f"Tenant ID from JWT: {token_tenant_id}")
        if token_tenant_id:
            tenant_id = token_tenant_id
        
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Tenant ID not found. Cannot update vendor without tenant scope.",
                    error_code="TENANT_NOT_FOUND",
                ),
            )

        # Final tenant_id to use for query and/or update
        logger.debug(f"Final tenant_id to use: {tenant_id}")

        # Fetch vendor with tenant scoping
        query = db.query(Vendor).filter(Vendor.vendor_id == vendor_id)
        if tenant_id:
            query = query.filter(Vendor.tenant_id == tenant_id)

        db_vendor = query.first()

        if not db_vendor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vendor with ID '{vendor_id}' not found"
                            f"{' in tenant ' + tenant_id if tenant_id else ''}",
                    error_code="VENDOR_NOT_FOUND",
                ),
            )

        # Prepare update data
        update_data = vendor_update.dict(exclude_unset=True)

        # Normalize vendor_code
        if "code" in update_data:
            update_data["vendor_code"] = update_data.pop("code")


        update_data.pop("tenant_id")  # Prevent changing tenant_id via update
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="No valid fields provided for update",
                    error_code="NO_UPDATE_FIELDS",
                ),
            )

        # 🔍 Capture old values before update
        old_values = {}
        for key in update_data.keys():
            old_val = getattr(db_vendor, key, None)
            if old_val is not None:
                old_values[key] = str(old_val) if not isinstance(old_val, (str, int, float, bool)) else old_val

        # Apply updates
        for key, value in update_data.items():
            setattr(db_vendor, key, value)

        db.commit()
        db.refresh(db_vendor)

        # 🔍 Capture new values after update
        new_values = {}
        for key in update_data.keys():
            new_val = getattr(db_vendor, key, None)
            if new_val is not None:
                new_values[key] = str(new_val) if not isinstance(new_val, (str, int, float, bool)) else new_val

        # 🔍 Audit Log: Vendor Update
        try:
            changed_fields = list(update_data.keys())
            fields_str = ", ".join(changed_fields) if changed_fields else "details"
            
            log_audit(
                db=db,
                tenant_id=db_vendor.tenant_id,
                module="vendor",
                action="UPDATE",
                user_data=user_data,
                description=f"Updated vendor '{db_vendor.name}' - changed fields: {fields_str}",
                new_values={"old": old_values, "new": new_values},
                request=request
            )
            logger.info(f"Audit log created for vendor update")
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for vendor update: {str(audit_error)}", exc_info=True)

        return ResponseWrapper.success(
            data=VendorResponse.model_validate(db_vendor, from_attributes=True),
            message=f"Vendor '{vendor_id}' updated successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise handle_db_error(e)

@router.patch("/{vendor_id}/toggle-status", status_code=status.HTTP_200_OK)
def toggle_vendor_status(
    vendor_id: int,
    request: Request,
    tenant_id: Optional[str] = Query(None, description="Tenant ID (Admin only)"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor.update"], check_tenant=True))
):
    """
    Toggle a vendor's active status.

    - Admin: can toggle status for any tenant by passing tenant_id.
    - Employee: can only toggle status within their tenant (tenant_id from token).
    - Other user types are forbidden.

    Args:
        vendor_id (int): the ID of the vendor to toggle.
        tenant_id (Optional[int]): tenant ID (required only if Admin toggles outside their tenant).

    Returns:
        ResponseWrapper: a successful response with the updated vendor data.
    """
    try:
        user_type = user_data.get("user_type")
        user_tenant_id = user_data.get("tenant_id")

        # Only Admin or Employee allowed
        if user_type not in ["admin", "employee"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Only Admin or Employee can toggle vendor status",
                    error_code="FORBIDDEN_USER_TYPE"
                )
            )

        # Determine effective tenant_id
        if user_type == "employee":
            tenant_id = user_tenant_id
        elif user_type == "admin":
            if tenant_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Admin must provide tenant_id to toggle status",
                        error_code="TENANT_ID_REQUIRED"
                    )
                )

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Tenant ID cannot be determined",
                    error_code="TENANT_ID_REQUIRED"
                )
            )

        # Fetch vendor within tenant
        db_vendor = db.query(Vendor).filter(
            Vendor.vendor_id == vendor_id,
            Vendor.tenant_id == tenant_id
        ).first()

        if not db_vendor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vendor with ID '{vendor_id}' not found in tenant '{tenant_id}'",
                    error_code="VENDOR_NOT_FOUND"
                )
            )

        # Toggle status
        old_status = db_vendor.is_active
        db_vendor = vendor_crud.toggle_active(db, vendor_id=vendor_id)
        db.commit()
        db.refresh(db_vendor)

        # 🔍 Audit Log: Status Toggle
        try:
            status_text = 'active' if db_vendor.is_active else 'inactive'
            log_audit(
                db=db,
                tenant_id=db_vendor.tenant_id,
                module="vendor",
                action="UPDATE",
                user_data=user_data,
                description=f"Toggled vendor '{db_vendor.name}' status to {status_text}",
                new_values={"old_status": old_status, "new_status": db_vendor.is_active},
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for status toggle: {str(audit_error)}")

        logger.info(
            f"Toggled vendor {vendor_id} status to "
            f"{'active' if db_vendor.is_active else 'inactive'} "
            f"by user_type={user_type}, tenant_id={tenant_id}"
        )

        return ResponseWrapper.success(
            data=VendorResponse.model_validate(db_vendor, from_attributes=True),
            message=f"Vendor '{vendor_id}' is now {'active' if db_vendor.is_active else 'inactive'}"
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while toggling vendor {vendor_id} status: {e}")
        raise handle_http_error(e)

# @router.delete("/{vendor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vendor(
    vendor_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor.delete"], check_tenant=True))
):
    """
    Delete a vendor by ID.
    """
    try:
        db_vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()

        if not db_vendor:
            logger.warning(f"Vendor delete failed - not found: {vendor_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vendor with ID '{vendor_id}' not found",
                    error_code=status.HTTP_404_NOT_FOUND,
                ),
            )

        db.delete(db_vendor)
        db.commit()

        logger.info(f"Vendor deleted successfully: {vendor_id}")
        return None

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while deleting vendor {vendor_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message=f"Unexpected error while deleting vendor '{vendor_id}'",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"error": str(e)},
            ),
        )

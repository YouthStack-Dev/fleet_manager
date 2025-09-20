from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.models.vendor import Vendor
from app.schemas.vendor import VendorCreate, VendorUpdate, VendorResponse, VendorPaginationResponse
from app.utils.pagination import paginate_query
from app.utils.response_utils import ResponseWrapper, handle_db_error
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger
from app.crud.tenant import tenant_crud
from app.crud.vendor import vendor_crud

logger = get_logger(__name__)
router = APIRouter(prefix="/vendors", tags=["vendors"])

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_vendor(
    vendor: VendorCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor.create"], check_tenant=False)),
):
    """
    Create a new vendor under a tenant.

    **Required permissions:** `vendor.create`
    """
    try:
        logger.info(f"Create vendor request: {vendor.dict()}")

        # Determine tenant_id from JWT or request
        tenant_id = getattr(user_data, "tenant_id", None) or vendor.tenant_id
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Tenant ID is required",
                    error_code=status.HTTP_400_BAD_REQUEST,
                ),
            )

        # Validate tenant exists and is active
        tenant = tenant_crud.get_by_id(db, tenant_id=tenant_id)
        if not tenant or not tenant.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Tenant '{tenant_id}' not found or inactive",
                    error_code=status.HTTP_404_NOT_FOUND,
                ),
            )

        # Check for duplicates using CRUD method
        existing = vendor_crud.get_by_code(db, tenant_id=tenant.tenant_id, vendor_code=vendor.vendor_code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ResponseWrapper.error(
                    message=f"Vendor with code '{vendor.vendor_code}' already exists in this tenant",
                    error_code=status.HTTP_409_CONFLICT,
                ),
            )

        # Create vendor using CRUD
        logger.debug(f"Creating vendor: {vendor.dict()}")
        db_vendor = vendor_crud.create(db, obj_in=vendor)
        db.commit()
        db.refresh(db_vendor)

        logger.info(f"Vendor created successfully: {db_vendor.vendor_id}")

        return ResponseWrapper.success(
            data=VendorResponse.model_validate(db_vendor, from_attributes=True),
            message="Vendor created successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise handle_db_error(e) 

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while creating vendor: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Unexpected server error while creating vendor",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor.read"], check_tenant=True))
):
    """
    Fetch paginated list of vendors with optional filters.
    """
    try:
        query = db.query(Vendor)

        if name:
            query = query.filter(Vendor.name.ilike(f"%{name}%"))
        if code:
            query = query.filter(Vendor.vendor_code.ilike(f"%{code}%"))
        if is_active is not None:
            query = query.filter(Vendor.is_active == is_active)

        total, items = paginate_query(query, skip, limit)
        vendors = [VendorResponse.model_validate(v, from_attributes=True) for v in items]

        logger.info(f"Fetched {len(vendors)} vendors (total={total}, skip={skip}, limit={limit})")

        return ResponseWrapper.success(
            data=VendorPaginationResponse(total=total, items=vendors),
            message="Vendors fetched successfully"
        )

    except Exception as e:
        logger.exception(f"Unexpected error while fetching vendors: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Unexpected error while fetching vendors",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"error": str(e)},
            ),
        )


@router.get("/{vendor_id}", status_code=status.HTTP_200_OK)
def read_vendor(
    vendor_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor.read"], check_tenant=True))
):
    """
    Fetch a single vendor by ID.
    """
    try:
        db_vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()

        if not db_vendor:
            logger.warning(f"Vendor fetch failed - not found: {vendor_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vendor with ID '{vendor_id}' not found",
                    error_code=status.HTTP_404_NOT_FOUND,
                ),
            )

        logger.info(f"Vendor fetched successfully: {vendor_id}")

        return ResponseWrapper.success(
            data=VendorResponse.model_validate(db_vendor, from_attributes=True),
            message="Vendor fetched successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while fetching vendor {vendor_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message=f"Unexpected error while fetching vendor '{vendor_id}'",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"error": str(e)},
            ),
        )


@router.put("/{vendor_id}", status_code=status.HTTP_200_OK)
def update_vendor(
    vendor_id: int,
    vendor_update: VendorUpdate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor.update"], check_tenant=True))
):
    """
    Update a vendor by ID.
    """
    try:
        db_vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
        if not db_vendor:
            logger.warning(f"Vendor update failed - not found: {vendor_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vendor with ID '{vendor_id}' not found",
                    error_code=status.HTTP_404_NOT_FOUND,
                ),
            )

        update_data = vendor_update.dict(exclude_unset=True)
        if "code" in update_data:
            update_data["vendor_code"] = update_data.pop("code")

        if not update_data:
            logger.warning(f"No update fields provided for vendor: {vendor_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="No valid fields provided for update",
                    error_code=status.HTTP_400_BAD_REQUEST,
                ),
            )

        for key, value in update_data.items():
            setattr(db_vendor, key, value)

        db.commit()
        db.refresh(db_vendor)

        logger.info(f"Vendor updated successfully: {vendor_id}")

        return ResponseWrapper.success(
            data=VendorResponse.model_validate(db_vendor, from_attributes=True),
            message=f"Vendor '{vendor_id}' updated successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while updating vendor {vendor_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message=f"Unexpected error while updating vendor '{vendor_id}'",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"error": str(e)},
            ),
        )


@router.patch("/{vendor_id}/toggle-status", status_code=status.HTTP_200_OK)
def toggle_vendor_status(
    vendor_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["vendor.update"], check_tenant=True))
):
    """
    Toggle the active/inactive status of a vendor.
    """
    try:
        db_vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()

        if not db_vendor:
            logger.warning(f"Vendor toggle failed - not found: {vendor_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Vendor with ID '{vendor_id}' not found",
                    error_code=status.HTTP_404_NOT_FOUND,
                ),
            )

        db_vendor.is_active = not db_vendor.is_active
        db.commit()
        db.refresh(db_vendor)

        logger.info(
            f"Toggled vendor {vendor_id} status to {'active' if db_vendor.is_active else 'inactive'}"
        )

        return ResponseWrapper.success(
            data=VendorResponse.model_validate(db_vendor, from_attributes=True),
            message=f"Vendor '{vendor_id}' is now {'active' if db_vendor.is_active else 'inactive'}"
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while toggling vendor {vendor_id} status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message=f"Unexpected error while toggling vendor '{vendor_id}' status",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"error": str(e)},
            ),
        )


@router.delete("/{vendor_id}", status_code=status.HTTP_204_NO_CONTENT)
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

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.database.session import get_db
from app.models.escort import Escort
from app.models.vendor import Vendor
from app.schemas.escort import EscortCreate, EscortUpdate, EscortResponse
from app.crud.escort import (
    get_escorts, get_escort, create_escort, update_escort,
    delete_escort, get_available_escorts, get_escort_by_phone
)
from common_utils.auth.permission_checker import PermissionChecker
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from app.utils.audit_helper import log_audit
from sqlalchemy.exc import SQLAlchemyError
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/escorts", tags=["escorts"])


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=EscortResponse)
def create_escort_endpoint(
    escort: EscortCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["escort.create"], check_tenant=True)),
):
    """
    Create a new escort for the tenant.
    """
    try:
        tenant_id = user_data.get("tenant_id")
        user_id = user_data.get("user_id")

        logger.info(f"Creating escort for tenant {tenant_id}: {escort.name}")

        # Validate vendor belongs to tenant
        vendor = db.query(Vendor).filter(
            Vendor.vendor_id == escort.vendor_id,
            Vendor.tenant_id == tenant_id
        ).first()

        if not vendor:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Vendor not found for this tenant",
                    error_code="VENDOR_NOT_FOUND",
                ),
            )

        # Check if phone number already exists
        existing_escort = get_escort_by_phone(db, escort.phone, tenant_id)
        if existing_escort:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Phone number already registered for another escort",
                    error_code="PHONE_EXISTS",
                ),
            )

        # Create escort
        db_escort = create_escort(db, escort, tenant_id)

        # Audit log
        try:
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="escort",
                action="CREATE",
                user_data=user_data,
                description=f"Created escort '{escort.name}' (ID: {db_escort.escort_id})",
                new_values={
                    "escort_id": db_escort.escort_id,
                    "name": db_escort.name,
                    "phone": db_escort.phone,
                    "vendor_id": db_escort.vendor_id,
                },
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for escort creation: {str(audit_error)}")

        logger.info(f"Escort created successfully: {db_escort.escort_id}")
        return db_escort

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("Database error occurred while creating escort")
        raise handle_db_error(e)
    except Exception as e:
        logger.exception("Unexpected error occurred while creating escort")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Internal server error",
                error_code="INTERNAL_ERROR",
            ),
        )


@router.get("/", response_model=List[EscortResponse])
def get_escorts_endpoint(
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["escort.read"], check_tenant=True)),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    vendor_id: Optional[int] = Query(None, description="Filter by vendor ID"),
    available_only: bool = Query(False, description="Show only available escorts"),
):
    """
    Get all escorts for the tenant with optional filtering.
    """
    try:
        tenant_id = user_data.get("tenant_id")

        if available_only:
            escorts = get_available_escorts(db, tenant_id)
        else:
            escorts = get_escorts(db, tenant_id, skip, limit)

        # Filter by vendor if specified
        if vendor_id:
            escorts = [e for e in escorts if e.vendor_id == vendor_id]

        logger.info(f"Retrieved {len(escorts)} escorts for tenant {tenant_id}")
        return escorts

    except SQLAlchemyError as e:
        logger.exception("Database error occurred while fetching escorts")
        raise handle_db_error(e)
    except Exception as e:
        logger.exception("Unexpected error occurred while fetching escorts")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Internal server error",
                error_code="INTERNAL_ERROR",
            ),
        )


@router.get("/{escort_id}", response_model=EscortResponse)
def get_escort_endpoint(
    escort_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["escort.read"], check_tenant=True)),
):
    """
    Get a specific escort by ID.
    """
    try:
        tenant_id = user_data.get("tenant_id")

        escort = get_escort(db, escort_id, tenant_id)
        if not escort:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Escort not found",
                    error_code="ESCORT_NOT_FOUND",
                ),
            )

        return escort

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("Database error occurred while fetching escort")
        raise handle_db_error(e)
    except Exception as e:
        logger.exception("Unexpected error occurred while fetching escort")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Internal server error",
                error_code="INTERNAL_ERROR",
            ),
        )


@router.put("/{escort_id}", response_model=EscortResponse)
def update_escort_endpoint(
    escort_id: int,
    escort_update: EscortUpdate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["escort.update"], check_tenant=True)),
):
    """
    Update an escort's information.
    """
    try:
        tenant_id = user_data.get("tenant_id")
        user_id = user_data.get("user_id")

        logger.info(f"Updating escort {escort_id} for tenant {tenant_id}")

        # Check if escort exists
        existing_escort = get_escort(db, escort_id, tenant_id)
        if not existing_escort:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Escort not found",
                    error_code="ESCORT_NOT_FOUND",
                ),
            )

        # Check phone uniqueness if phone is being updated
        if escort_update.phone and escort_update.phone != existing_escort.phone:
            phone_exists = get_escort_by_phone(db, escort_update.phone, tenant_id)
            if phone_exists:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Phone number already registered for another escort",
                        error_code="PHONE_EXISTS",
                    ),
                )

        # Validate vendor if being updated
        if escort_update.vendor_id:
            vendor = db.query(Vendor).filter(
                Vendor.vendor_id == escort_update.vendor_id,
                Vendor.tenant_id == tenant_id
            ).first()
            if not vendor:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Vendor not found for this tenant",
                        error_code="VENDOR_NOT_FOUND",
                    ),
                )

        # Update escort
        updated_escort = update_escort(db, escort_id, escort_update, tenant_id)

        # Audit log
        try:
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="escort",
                action="UPDATE",
                user_data=user_data,
                description=f"Updated escort '{updated_escort.name}' (ID: {escort_id})",
                old_values={
                    "name": existing_escort.name,
                    "phone": existing_escort.phone,
                    "vendor_id": existing_escort.vendor_id,
                },
                new_values={
                    "name": updated_escort.name,
                    "phone": updated_escort.phone,
                    "vendor_id": updated_escort.vendor_id,
                },
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for escort update: {str(audit_error)}")

        logger.info(f"Escort {escort_id} updated successfully")
        return updated_escort

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("Database error occurred while updating escort")
        raise handle_db_error(e)
    except Exception as e:
        logger.exception("Unexpected error occurred while updating escort")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Internal server error",
                error_code="INTERNAL_ERROR",
            ),
        )


@router.delete("/{escort_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_escort_endpoint(
    escort_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["escort.delete"], check_tenant=True)),
):
    """
    Delete an escort.
    """
    try:
        tenant_id = user_data.get("tenant_id")
        user_id = user_data.get("user_id")

        logger.info(f"Deleting escort {escort_id} for tenant {tenant_id}")

        # Check if escort exists
        escort = get_escort(db, escort_id, tenant_id)
        if not escort:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message="Escort not found",
                    error_code="ESCORT_NOT_FOUND",
                ),
            )

        # Delete escort
        deleted = delete_escort(db, escort_id, tenant_id)

        if deleted:
            # Audit log
            try:
                log_audit(
                    db=db,
                    tenant_id=tenant_id,
                    module="escort",
                    action="DELETE",
                    user_data=user_data,
                    description=f"Deleted escort '{escort.name}' (ID: {escort_id})",
                    old_values={
                        "escort_id": escort_id,
                        "name": escort.name,
                        "phone": escort.phone,
                        "vendor_id": escort.vendor_id,
                    },
                )
            except Exception as audit_error:
                logger.error(f"Failed to create audit log for escort deletion: {str(audit_error)}")

            logger.info(f"Escort {escort_id} deleted successfully")
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ResponseWrapper.error(
                    message="Failed to delete escort",
                    error_code="DELETE_FAILED",
                ),
            )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("Database error occurred while deleting escort")
        raise handle_db_error(e)
    except Exception as e:
        logger.exception("Unexpected error occurred while deleting escort")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Internal server error",
                error_code="INTERNAL_ERROR",
            ),
        )


@router.get("/available/", response_model=List[EscortResponse])
def get_available_escorts_endpoint(
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["escort.read"], check_tenant=True)),
):
    """
    Get all available escorts for the tenant.
    """
    try:
        tenant_id = user_data.get("tenant_id")

        escorts = get_available_escorts(db, tenant_id)

        logger.info(f"Retrieved {len(escorts)} available escorts for tenant {tenant_id}")
        return escorts

    except SQLAlchemyError as e:
        logger.exception("Database error occurred while fetching available escorts")
        raise handle_db_error(e)
    except Exception as e:
        logger.exception("Unexpected error occurred while fetching available escorts")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Internal server error",
                error_code="INTERNAL_ERROR",
            ),
        )
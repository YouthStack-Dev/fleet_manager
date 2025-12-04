from ast import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.crud.cutoff import cutoff_crud
from app.crud.tenant import tenant_crud
from app.schemas.cutoff import CutoffOut, CutoffUpdate
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from common_utils.auth.permission_checker import PermissionChecker
from sqlalchemy.exc import SQLAlchemyError
from app.core.logging_config import get_logger
from app.utils.audit_helper import log_audit

logger = get_logger(__name__)
router = APIRouter(prefix="/cutoffs", tags=["cutoffs"])


@router.get("/", status_code=status.HTTP_200_OK)
def get_cutoffs(
    tenant_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["cutoff.read"], check_tenant=True)),
):
    """
    Fetch cutoff(s):
    - Admin → can fetch all or specific tenant by tenant_id
    - Employee → can fetch only their own tenant (tenant_id from token)
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # Employee restriction
        if user_type == "employee":
            tenant_id = token_tenant_id
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )

        cutoffs_response = []

        # Admin can fetch all if tenant_id not provided
        if user_type == "admin" and tenant_id is None:
            tenants = tenant_crud.get_all(db)
            for tenant in tenants:
                cutoff = cutoff_crud.ensure_cutoff(db, tenant_id=tenant.tenant_id)
                cutoffs_response.append(CutoffOut.model_validate(cutoff, from_attributes=True))
        else:
            # tenant_id must exist
            tenant = tenant_crud.get_by_id(db, tenant_id=tenant_id)
            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        message=f"Tenant {tenant_id} not found",
                        error_code="TENANT_NOT_FOUND",
                    ),
                )
            cutoff = cutoff_crud.ensure_cutoff(db, tenant_id=tenant_id)
            cutoffs_response.append(CutoffOut.model_validate(cutoff, from_attributes=True))

        db.commit()  # commit any default created
        return ResponseWrapper.success(
            data={"cutoffs": cutoffs_response},
            message="Cutoffs fetched successfully"
        )

    except SQLAlchemyError as e:
        logger.exception(f"DB error fetching cutoffs: {e}")
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error fetching cutoffs: {e}")
        raise handle_http_error(e)


@router.put("/",status_code=status.HTTP_200_OK)
def update_cutoff(
    update_in: CutoffUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["cutoff.update"], check_tenant=True)),
):
    """
    Update cutoff for a tenant.
    - employee → only within their tenant
    - admin → can update any tenant
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")
        if user_type == "admin" and not update_in.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Admin must provide tenant_id to update cutoff",
                    error_code="TENANT_ID_REQUIRED",
                ),
            )
        tenant_id = update_in.tenant_id if user_type == "admin" else token_tenant_id

        if user_type == "employee" and tenant_id != token_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You cannot update cutoff outside your tenant",
                    error_code="TENANT_FORBIDDEN",
                ),
            )

        # Ensure tenant exists
        tenant = tenant_crud.get_by_id(db, tenant_id=tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND",
                ),
            )

        cutoff = cutoff_crud.update_by_tenant(db, tenant_id=tenant_id, obj_in=update_in)
        db.commit()
        db.refresh(cutoff)

        # 🔍 Audit Log: Cutoff Update
        try:
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="cutoff",
                action="UPDATE",
                user_data=user_data,
                description=f"Updated cutoff times for tenant {tenant_id}",
                new_values={
                    "booking_login_cutoff": str(update_in.booking_login_cutoff) if update_in.booking_login_cutoff else None,
                    "cancel_login_cutoff": str(update_in.cancel_login_cutoff) if update_in.cancel_login_cutoff else None,
                    "booking_logout_cutoff": str(update_in.booking_logout_cutoff) if update_in.booking_logout_cutoff else None,
                    "cancel_logout_cutoff": str(update_in.cancel_logout_cutoff) if update_in.cancel_logout_cutoff else None,
                    "medical_emergency_booking_cutoff": str(update_in.medical_emergency_booking_cutoff) if update_in.medical_emergency_booking_cutoff else None,
                    "medical_emergency_cancel_cutoff": str(update_in.medical_emergency_cancel_cutoff) if update_in.medical_emergency_cancel_cutoff else None,
                    "adhoc_booking_cutoff": str(update_in.adhoc_booking_cutoff) if update_in.adhoc_booking_cutoff else None,
                    "allow_adhoc_booking": update_in.allow_adhoc_booking,
                    "allow_medical_emergency_booking": update_in.allow_medical_emergency_booking,
                    "allow_medical_emergency_cancel": update_in.allow_medical_emergency_cancel,
                },
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for cutoff update: {str(audit_error)}")

        return ResponseWrapper.success(
            data={"cutoff": CutoffOut.model_validate(cutoff, from_attributes=True)},
            message=f"Cutoff updated successfully for tenant {tenant_id}"
        )

    except SQLAlchemyError as e:
        logger.exception(f"DB error updating cutoff for tenant {tenant_id}: {e}")
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error updating cutoff for tenant {tenant_id}: {e}")
        raise handle_http_error(e)

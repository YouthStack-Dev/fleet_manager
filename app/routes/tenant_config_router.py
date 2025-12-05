from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.params import Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import time

from app.database.session import get_db
from app.models.tenant_config import TenantConfig
from app.schemas.tenant_config import TenantConfigCreate, TenantConfigUpdate, TenantConfigResponse
from app.crud.tenant_config import tenant_config_crud
from common_utils.auth.permission_checker import PermissionChecker
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from app.utils.audit_helper import log_audit
from sqlalchemy.exc import SQLAlchemyError
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/tenant-config", tags=["tenant-config"])


def resolve_tenant_id(user_data: dict, tenant_id_param: Optional[str] = None) -> str:
    """
    Resolve tenant_id based on user type.
    
    Args:
        user_data: User data from token
        tenant_id_param: tenant_id from query parameter (for admin users)
    
    Returns:
        Resolved tenant_id
        
    Raises:
        HTTPException: If tenant_id cannot be resolved
    """
    user_type = user_data.get("user_type")
    
    if user_type in ["employee", "vendor"]:
        resolved_tenant_id = user_data.get("tenant_id")
        if not resolved_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Tenant ID missing in token",
                    error_code="TENANT_ID_REQUIRED"
                )
            )
    elif user_type == "admin":
        if tenant_id_param:
            resolved_tenant_id = tenant_id_param
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Tenant ID is required as query parameter for admin",
                    error_code="TENANT_ID_REQUIRED"
                )
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error(
                message="Unauthorized user type for this operation",
                error_code="UNAUTHORIZED_USER_TYPE"
            )
        )
    
    return resolved_tenant_id


@router.get("/", response_model=TenantConfigResponse)
def get_tenant_config(
    tenant_id: Optional[str] = Query(None, description="Tenant ID (required for admin, automatic for employee/vendor)"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["tenant_config.read"], check_tenant=False)),
):
    """
    Get tenant configuration.
    
    Rules:
    - Admin: Must provide tenant_id as query parameter
    - Employee/Vendor: tenant_id taken from token
    """
    try:
        resolved_tenant_id = resolve_tenant_id(user_data, tenant_id)

        config = tenant_config_crud.get_by_tenant(db, tenant_id=resolved_tenant_id)
        if not config:
            # Return default config if not exists
            config = tenant_config_crud.ensure_config(db, resolved_tenant_id)

        logger.info(f"Retrieved tenant config for tenant {resolved_tenant_id}")
        return config

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("Database error occurred while fetching tenant config")
        raise handle_db_error(e)
    except Exception as e:
        logger.exception("Unexpected error occurred while fetching tenant config")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Internal server error",
                error_code="INTERNAL_ERROR",
            ),
        )


@router.put("/", response_model=TenantConfigResponse)
def update_tenant_config(
    config_update: TenantConfigUpdate,
    tenant_id: Optional[str] = Query(None, description="Tenant ID (required for admin, automatic for employee/vendor)"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["tenant_config.update", "tenant_config.escort"], check_tenant=False)),
):
    """
    Update tenant configuration.
    
    Rules:
    - Admin: Must provide tenant_id as query parameter
    - Employee/Vendor: tenant_id taken from token
    """
    try:
        resolved_tenant_id = resolve_tenant_id(user_data, tenant_id)

        user_id = user_data.get("user_id")

        logger.info(f"Updating tenant config for tenant {resolved_tenant_id}")

        # Update config
        updated_config = tenant_config_crud.update_by_tenant(
            db, tenant_id=resolved_tenant_id, obj_in=config_update
        )

        # Audit log
        try:
            log_audit(
                db=db,
                tenant_id=resolved_tenant_id,
                module="tenant_config",
                action="UPDATE",
                user_data=user_data,
                description=f"Updated tenant configuration",
                old_values={},  # Could be enhanced to track old values
                new_values={
                    "escort_required_start_time": str(config_update.escort_required_start_time) if config_update.escort_required_start_time else None,
                    "escort_required_end_time": str(config_update.escort_required_end_time) if config_update.escort_required_end_time else None,
                    "escort_required_for_women": config_update.escort_required_for_women,
                    "login_boarding_otp": config_update.login_boarding_otp,
                    "login_deboarding_otp": config_update.login_deboarding_otp,
                    "logout_boarding_otp": config_update.logout_boarding_otp,
                    "logout_deboarding_otp": config_update.logout_deboarding_otp,
                },
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for tenant config update: {str(audit_error)}")

        logger.info(f"Tenant config updated successfully for tenant {resolved_tenant_id}")
        return updated_config

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("Database error occurred while updating tenant config")
        raise handle_db_error(e)
    except Exception as e:
        logger.exception("Unexpected error occurred while updating tenant config")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Internal server error",
                error_code="INTERNAL_ERROR",
            ),
        )


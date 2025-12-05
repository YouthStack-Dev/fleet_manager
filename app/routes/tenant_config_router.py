from fastapi import APIRouter, Depends, HTTPException, status
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


@router.get("/", response_model=TenantConfigResponse)
def get_tenant_config(
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["tenant_config.read"], check_tenant=True)),
):
    """
    Get tenant configuration for the authenticated tenant.
    """
    try:
        tenant_id = user_data.get("tenant_id")

        config = tenant_config_crud.get_by_tenant(db, tenant_id=tenant_id)
        if not config:
            # Return default config if not exists
            config = tenant_config_crud.ensure_config(db, tenant_id)

        logger.info(f"Retrieved tenant config for tenant {tenant_id}")
        return config

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
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["tenant_config.update", "tenant_config.escort"], check_tenant=True)),
):
    """
    Update tenant configuration for the authenticated tenant.
    """
    try:
        tenant_id = user_data.get("tenant_id")
        user_id = user_data.get("user_id")

        logger.info(f"Updating tenant config for tenant {tenant_id}")

        # Update config
        updated_config = tenant_config_crud.update_by_tenant(
            db, tenant_id=tenant_id, obj_in=config_update
        )

        # Audit log
        try:
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="tenant_config",
                action="UPDATE",
                user_data=user_data,
                description=f"Updated tenant configuration",
                old_values={},  # Could be enhanced to track old values
                new_values={
                    "escort_required_start_time": str(config_update.escort_required_start_time) if config_update.escort_required_start_time else None,
                    "escort_required_end_time": str(config_update.escort_required_end_time) if config_update.escort_required_end_time else None,
                    "escort_required_for_women": config_update.escort_required_for_women,
                },
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for tenant config update: {str(audit_error)}")

        logger.info(f"Tenant config updated successfully for tenant {tenant_id}")
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


@router.post("/initialize", status_code=status.HTTP_201_CREATED, response_model=TenantConfigResponse)
def initialize_tenant_config(
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["tenant_config.create", "tenant_config.seed"], check_tenant=True)),
):
    """
    Initialize tenant configuration with default values.
    Only creates if config doesn't already exist.
    """
    try:
        tenant_id = user_data.get("tenant_id")
        user_id = user_data.get("user_id")

        logger.info(f"Initializing tenant config for tenant {tenant_id}")

        # Check if config already exists
        existing_config = tenant_config_crud.get_by_tenant(db, tenant_id=tenant_id)
        if existing_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="Tenant config already exists",
                    error_code="CONFIG_EXISTS",
                ),
            )

        # Create default config
        config_data = TenantConfigCreate(
            tenant_id=tenant_id,
            escort_required_for_women=True
        )
        db_config = tenant_config_crud.create_with_tenant(db, obj_in=config_data)

        # Audit log
        try:
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="tenant_config",
                action="CREATE",
                user_data=user_data,
                description=f"Initialized tenant configuration with defaults",
                new_values={
                    "escort_required_for_women": True,
                },
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for tenant config initialization: {str(audit_error)}")

        logger.info(f"Tenant config initialized successfully for tenant {tenant_id}")
        return db_config

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("Database error occurred while initializing tenant config")
        raise handle_db_error(e)
    except Exception as e:
        logger.exception("Unexpected error occurred while initializing tenant config")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Internal server error",
                error_code="INTERNAL_ERROR",
            ),
        )
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.schemas.audit_log import AuditLogResponse, AuditLogFilter
from app.crud.audit_log import audit_log
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from common_utils.auth.permission_checker import PermissionChecker
from sqlalchemy.exc import SQLAlchemyError
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("/module/{module_name}", status_code=status.HTTP_200_OK)
def get_audit_by_module(
    module_name: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    tenant_id: Optional[str] = Query(None, description="Tenant ID for filtering (required for admins)"),
    employee_id: Optional[int] = Query(None, description="Employee ID filter (only for employee module)"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["audit_log.read"], check_tenant=True)),
):
    """
    Get all audit logs for a specific module (employee, driver, vehicle, etc.)
    
    Automatically filters by tenant_id from user's token.
    
    Example: GET /api/audit-logs/module/employee
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # 🚫 Drivers forbidden
        if user_type == "driver":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to view audit logs",
                    error_code="FORBIDDEN",
                ),
            )

        # Validate module name
        allowed_modules = [
            "employee", "admin", "driver", "vehicle", "vendor", "vendor_user",
            "booking", "team", "tenant", "shift", "cutoff", "vehicle_type", "weekoff_config"
        ]
        if module_name.lower() not in allowed_modules:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message=f"Invalid module name: {module_name}",
                    error_code="INVALID_MODULE",
                ),
            )

        # 🔒 Tenant filtering and module restrictions
        tenant_filter = None
        
        # For employees - must use their tenant_id
        if user_type == "employee":
            if not token_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
            tenant_filter = token_tenant_id
        
        # For admins - must provide tenant_id in query parameter
        elif user_type == "admin":
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Tenant ID query parameter is required for admin",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
            tenant_filter = tenant_id
        
        # For vendors - only allow vendor-related modules
        elif user_type == "vendor":
            allowed_vendor_modules = ["driver", "vehicle", "vehicle_type", "vendor_user"]
            if module_name.lower() not in allowed_vendor_modules:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message=f"Vendors can only view audit logs for: {', '.join(allowed_vendor_modules)}",
                        error_code="MODULE_FORBIDDEN",
                    ),
                )

        # Create filter with module and tenant
        filters = AuditLogFilter(
            module=module_name.lower(),
            tenant_id=tenant_filter,
            page=page,
            page_size=page_size
        )

        # Add employee_id filter if module is employee
        if module_name.lower() == "employee" and employee_id is not None:
            filters.employee_id = employee_id
            logger.info(f"Applying employee_id filter: {employee_id} for module '{module_name}'")

        # Get filtered audit logs
        logs, total_count = audit_log.get_filtered(db=db, filters=filters)

        # Convert to response format
        logs_response = [AuditLogResponse.model_validate(log, from_attributes=True) for log in logs]

        logger.info(
            f"Retrieved {len(logs_response)} audit logs for module '{module_name}' "
            f"(page {page}, total {total_count}) by {user_type}"
        )

        return ResponseWrapper.success(
            data={
                "module": module_name,
                "audit_logs": logs_response,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_count": total_count,
                    "total_pages": (total_count + page_size - 1) // page_size
                }
            },
            message=f"Audit logs for {module_name} retrieved successfully",
        )

    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while fetching audit logs for module {module_name}: {str(e)}")
        raise handle_http_error(e)


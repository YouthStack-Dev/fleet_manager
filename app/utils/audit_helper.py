"""
Simplified audit helper utility
"""
from sqlalchemy.orm import Session
from fastapi import Request
from typing import Dict, Any, Optional
from app.services.audit_service import audit_service
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def log_audit(
    db: Session,
    tenant_id: str,
    module: str,
    action: str,
    user_data: Dict[str, Any],
    description: str,
    new_values: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None
):
    """
    Simplified audit logging helper
    
    Args:
        db: Database session
        tenant_id: Tenant ID
        module: Module name ('employee', 'driver', 'vehicle', etc.)
        action: Action performed ('CREATE', 'UPDATE', 'DELETE')
        user_data: User data from token
        description: Human-readable description
        new_values: New values/details
        request: FastAPI request object
    """
    try:
        user_type = user_data.get("user_type")
        user_id = user_data.get("user_id")
        
        # Get user details from database
        user_details = audit_service.get_user_details(db, user_type, user_id)
        
        # Log the action
        audit_service.log_audit(
            db=db,
            tenant_id=tenant_id,
            module=module,
            action=action,
            user_type=user_type,
            user_id=user_id,
            user_name=user_details["name"],
            user_email=user_details["email"],
            description=description,
            new_values=new_values,
            request=request
        )
        db.commit()
        logger.info(f"Audit log created for {module}: {description}")
        
    except Exception as audit_error:
        logger.error(f"Failed to create audit log: {str(audit_error)}", exc_info=True)

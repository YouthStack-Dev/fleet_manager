from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, Union
from fastapi import Request
from app.models.audit_log import AuditLog, ActionEnum, EntityTypeEnum
from app.schemas.audit_log import AuditLogCreate
from app.crud.audit_log import audit_log


class AuditService:
    """
    Service for easy audit logging across the application
    """
    
    @staticmethod
    def log_action(
        db: Session,
        entity_type: EntityTypeEnum,
        entity_id: Union[str, int],
        action: ActionEnum,
        performed_by: Dict[str, Any],
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
        request: Optional[Request] = None,
        tenant_id: Optional[str] = None
    ) -> AuditLog:
        """
        Log an audit action
        
        Args:
            db: Database session
            entity_type: Type of entity being audited (EMPLOYEE, ADMIN, etc.)
            entity_id: ID of the entity
            action: Action performed (CREATE, UPDATE, DELETE, etc.)
            performed_by: Dict containing user info:
                - type: 'admin', 'employee', 'vendor_user'
                - id: User ID
                - name: User name
                - email: User email (optional)
            old_values: Previous values (for UPDATE actions)
            new_values: New values (for CREATE/UPDATE actions)
            description: Additional description
            request: FastAPI request object (to extract IP and user agent)
            tenant_id: Tenant ID if applicable
        """
        
        # Extract IP address and user agent from request if available
        ip_address = None
        user_agent = None
        if request:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent", None)
        
        # Create audit log entry
        audit_data = AuditLogCreate(
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            performed_by_type=performed_by.get("type"),
            performed_by_id=performed_by.get("id"),
            performed_by_name=performed_by.get("name"),
            performed_by_email=performed_by.get("email"),
            tenant_id=tenant_id,
            old_values=old_values,
            new_values=new_values,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        return audit_log.create(db=db, audit_log_data=audit_data)
    
    @staticmethod
    def log_employee_created(
        db: Session,
        employee_id: int,
        employee_data: Dict[str, Any],
        performed_by: Dict[str, Any],
        request: Optional[Request] = None,
        tenant_id: Optional[str] = None
    ) -> AuditLog:
        """
        Convenience method to log employee creation
        """
        description = f"{performed_by.get('name')} ({performed_by.get('email')}) created employee '{employee_data.get('name')}'"
        return AuditService.log_action(
            db=db,
            entity_type=EntityTypeEnum.EMPLOYEE,
            entity_id=employee_id,
            action=ActionEnum.CREATE,
            performed_by=performed_by,
            new_values=employee_data,
            description=description,
            request=request,
            tenant_id=tenant_id
        )
    
    @staticmethod
    def log_employee_updated(
        db: Session,
        employee_id: int,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any],
        performed_by: Dict[str, Any],
        request: Optional[Request] = None,
        tenant_id: Optional[str] = None
    ) -> AuditLog:
        """
        Convenience method to log employee update
        """
        # Build description with changed fields
        changed_fields = list(new_data.keys()) if new_data else []
        fields_str = ", ".join(changed_fields) if changed_fields else "details"
        description = f"{performed_by.get('name')} ({performed_by.get('email')}) updated employee {fields_str}"
        
        return AuditService.log_action(
            db=db,
            entity_type=EntityTypeEnum.EMPLOYEE,
            entity_id=employee_id,
            action=ActionEnum.UPDATE,
            performed_by=performed_by,
            old_values=old_data,
            new_values=new_data,
            description=description,
            request=request,
            tenant_id=tenant_id
        )
    
    @staticmethod
    def log_employee_deleted(
        db: Session,
        employee_id: int,
        employee_data: Dict[str, Any],
        performed_by: Dict[str, Any],
        request: Optional[Request] = None,
        tenant_id: Optional[str] = None
    ) -> AuditLog:
        """
        Convenience method to log employee deletion
        """
        description = f"{performed_by.get('name')} ({performed_by.get('email')}) deleted employee '{employee_data.get('name')}'"
        return AuditService.log_action(
            db=db,
            entity_type=EntityTypeEnum.EMPLOYEE,
            entity_id=employee_id,
            action=ActionEnum.DELETE,
            performed_by=performed_by,
            old_values=None,  # Simplified - no JSON data
            description=description,
            request=request,
            tenant_id=tenant_id
        )
    
    @staticmethod
    def sanitize_data(data: Dict[str, Any], fields_to_exclude: list = None) -> Dict[str, Any]:
        """
        Sanitize data before logging (remove sensitive fields like passwords)
        """
        if fields_to_exclude is None:
            fields_to_exclude = ['password', 'token', 'secret', 'api_key']
        
        sanitized = data.copy()
        for field in fields_to_exclude:
            if field in sanitized:
                sanitized[field] = "***REDACTED***"
        
        return sanitized


audit_service = AuditService()

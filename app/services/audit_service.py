from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from fastapi import Request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.models.audit_log import AuditLog

# India Standard Time
IST = ZoneInfo("Asia/Kolkata")
from app.schemas.audit_log import AuditLogCreate
from app.crud.audit_log import audit_log


class AuditService:
    """
    Simplified audit service - stores all data in JSON
    """
    
    @staticmethod
    def log_audit(
        db: Session,
        tenant_id: str,
        module: str,
        action: str,
        user_type: str,
        user_id: int,
        user_name: str,
        user_email: Optional[str] = None,
        description: Optional[str] = None,
        new_values: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None
    ) -> AuditLog:
        """
        Log an audit entry with all data in JSON
        
        Args:
            db: Database session
            tenant_id: Tenant ID
            module: Module name ('employee', 'driver', 'vehicle', etc.)
            action: Action performed ('CREATE', 'UPDATE', 'DELETE', etc.)
            user_type: Type of user ('admin', 'employee', 'vendor')
            user_id: User ID
            user_name: User name
            user_email: User email
            description: Human-readable description
            new_values: New values/details
            request: FastAPI request for IP/user agent
        """
        
        # Build audit_data JSON
        audit_data_json = {
            "action": action,
            "user": {
                "type": user_type,
                "id": user_id,
                "name": user_name,
                "email": user_email
            },
            "description": description,
            "new_values": new_values,
            "timestamp": datetime.now(IST).isoformat()
        }
        
        # Add request info if available
        if request:
            audit_data_json["ip_address"] = request.client.host if request.client else None
            audit_data_json["user_agent"] = request.headers.get("user-agent", None)
        
        # Create audit log entry
        audit_log_data = AuditLogCreate(
            tenant_id=tenant_id,
            module=module,
            audit_data=audit_data_json
        )
        
        return audit_log.create(db=db, audit_log_data=audit_log_data)
    
    @staticmethod
    def get_user_details(db: Session, user_type: str, user_id: int) -> Dict[str, Any]:
        """
        Helper to fetch user details from database
        Returns dict with name and email
        """
        user_name = "Unknown"
        user_email = None
        
        if user_type == "admin":
            from app.models.admin import Admin
            user_obj = db.query(Admin).filter(Admin.admin_id == user_id).first()
            if user_obj:
                user_name = user_obj.name
                user_email = user_obj.email
        elif user_type == "employee":
            from app.models.employee import Employee
            user_obj = db.query(Employee).filter(Employee.employee_id == user_id).first()
            if user_obj:
                user_name = user_obj.name
                user_email = user_obj.email
        elif user_type == "vendor":
            from app.models.vendor_user import VendorUser
            user_obj = db.query(VendorUser).filter(VendorUser.vendor_user_id == user_id).first()
            if user_obj:
                user_name = user_obj.name
                user_email = user_obj.email
        
        return {"name": user_name, "email": user_email}


audit_service = AuditService()

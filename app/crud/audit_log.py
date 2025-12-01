from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional, List
from datetime import datetime
from app.models.audit_log import AuditLog
from app.schemas.audit_log import AuditLogCreate, AuditLogFilter
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class CRUDAuditLog:
    def create(self, db: Session, *, audit_log_data: AuditLogCreate) -> AuditLog:
        """
        Create a new audit log entry
        """
        db_audit_log = AuditLog(**audit_log_data.model_dump())
        db.add(db_audit_log)
        db.commit()
        db.refresh(db_audit_log)
        return db_audit_log

    def get_by_id(self, db: Session, *, audit_id: int) -> Optional[AuditLog]:
        """
        Get a specific audit log by ID
        """
        return db.query(AuditLog).filter(AuditLog.audit_id == audit_id).first()

    def get_filtered(
        self,
        db: Session,
        *,
        filters: AuditLogFilter
    ) -> tuple[List[AuditLog], int]:
        """
        Get audit logs with filters and pagination
        Returns tuple of (records, total_count)
        """
        query = db.query(AuditLog)
        
        # Apply filters
        conditions = []
        
        if filters.tenant_id:
            conditions.append(AuditLog.tenant_id == filters.tenant_id)
        
        if filters.module:
            conditions.append(AuditLog.module == filters.module)
        
        if filters.start_date:
            conditions.append(AuditLog.created_at >= filters.start_date)
        
        if filters.employee_id:
            conditions.append(AuditLog.audit_data.op('->')('new_values').op('->>')('employee_id') == str(filters.employee_id))
            logger.info(f"Filtering audit logs by employee_id: {filters.employee_id}")
        
        if conditions:
            query = query.filter(and_(*conditions))
        
        # Get total count
        total_count = query.count()
        
        # Apply pagination
        skip = (filters.page - 1) * filters.page_size
        records = (
            query
            .order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(filters.page_size)
            .all()
        )
        
        return records, total_count

    def get_by_module(
        self,
        db: Session,
        *,
        module: str,
        tenant_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[AuditLog]:
        """
        Get all audit logs for a specific module and tenant
        """
        return (
            db.query(AuditLog)
            .filter(
                and_(
                    AuditLog.module == module,
                    AuditLog.tenant_id == tenant_id
                )
            )
            .order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )


audit_log = CRUDAuditLog()

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import Optional, List
from datetime import datetime
from app.models.audit_log import AuditLog
from app.schemas.audit_log import AuditLogCreate, AuditLogFilter


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

    def get_by_entity(
        self, 
        db: Session, 
        *, 
        entity_type: str, 
        entity_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[AuditLog]:
        """
        Get all audit logs for a specific entity
        """
        return (
            db.query(AuditLog)
            .filter(
                and_(
                    AuditLog.entity_type == entity_type,
                    AuditLog.entity_id == entity_id
                )
            )
            .order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

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
        
        if filters.entity_type:
            conditions.append(AuditLog.entity_type == filters.entity_type)
        
        if filters.entity_id:
            conditions.append(AuditLog.entity_id == filters.entity_id)
        
        if filters.action:
            conditions.append(AuditLog.action == filters.action)
        
        if filters.performed_by_type:
            conditions.append(AuditLog.performed_by_type == filters.performed_by_type)
        
        if filters.performed_by_id:
            conditions.append(AuditLog.performed_by_id == filters.performed_by_id)
        
        if filters.tenant_id:
            conditions.append(AuditLog.tenant_id == filters.tenant_id)
        
        if filters.start_date:
            conditions.append(AuditLog.created_at >= filters.start_date)
        
        if filters.end_date:
            conditions.append(AuditLog.created_at <= filters.end_date)
        
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

    def get_by_performer(
        self,
        db: Session,
        *,
        performed_by_type: str,
        performed_by_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> List[AuditLog]:
        """
        Get all audit logs for a specific user (performer)
        """
        return (
            db.query(AuditLog)
            .filter(
                and_(
                    AuditLog.performed_by_type == performed_by_type,
                    AuditLog.performed_by_id == performed_by_id
                )
            )
            .order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_tenant(
        self,
        db: Session,
        *,
        tenant_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[AuditLog]:
        """
        Get all audit logs for a specific tenant
        """
        return (
            db.query(AuditLog)
            .filter(AuditLog.tenant_id == tenant_id)
            .order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )


audit_log = CRUDAuditLog()

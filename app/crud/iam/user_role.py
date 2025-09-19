from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.models.iam import UserRole
from app.schemas.iam import UserRoleCreate, UserRoleUpdate
from app.crud.base import CRUDBase

class CRUDUserRole(CRUDBase[UserRole, UserRoleCreate, UserRoleUpdate]):
    def get_by_user_and_tenant(self, db: Session, *, user_id: int, tenant_id: str) -> List[UserRole]:
        return db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.tenant_id == tenant_id,
            UserRole.is_active == True
        ).all()
    
    def get_multi_by_filter(self, db: Session, *, filters: Dict = None, skip: int = 0, limit: int = 100) -> List[UserRole]:
        query = db.query(self.model)
        
        if filters:
            if "user_id" in filters:
                query = query.filter(UserRole.user_id == filters["user_id"])
            if "role_id" in filters:
                query = query.filter(UserRole.role_id == filters["role_id"])
            if "tenant_id" in filters:
                query = query.filter(UserRole.tenant_id == filters["tenant_id"])
        
        return query.offset(skip).limit(limit).all()
    
    def count(self, db: Session, *, filters: Dict = None) -> int:
        query = db.query(self.model)
        
        if filters:
            if "user_id" in filters:
                query = query.filter(UserRole.user_id == filters["user_id"])
            if "role_id" in filters:
                query = query.filter(UserRole.role_id == filters["role_id"])
            if "tenant_id" in filters:
                query = query.filter(UserRole.tenant_id == filters["tenant_id"])
        
        return query.count()

user_role_crud = CRUDUserRole(UserRole)

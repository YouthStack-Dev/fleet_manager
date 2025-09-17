from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.models.iam import Permission
from app.schemas.iam import PermissionCreate, PermissionUpdate
from app.crud.base import CRUDBase

class CRUDPermission(CRUDBase[Permission, PermissionCreate, PermissionUpdate]):
    def get_by_code(self, db: Session, *, module: str, action: str) -> Optional[Permission]:
        return db.query(Permission).filter(
            Permission.module == module,
            Permission.action == action
        ).first()
    
    def get_multi_by_filter(self, db: Session, *, filters: Dict = None, skip: int = 0, limit: int = 100) -> List[Permission]:
        query = db.query(self.model)
        
        if filters:
            if "module" in filters:
                query = query.filter(Permission.module == filters["module"])
            if "action" in filters:
                query = query.filter(Permission.action == filters["action"])
        
        return query.offset(skip).limit(limit).all()
    
    def count(self, db: Session, *, filters: Dict = None) -> int:
        query = db.query(self.model)
        
        if filters:
            if "module" in filters:
                query = query.filter(Permission.module == filters["module"])
            if "action" in filters:
                query = query.filter(Permission.action == filters["action"])
        
        return query.count()

permission_crud = CRUDPermission(Permission)

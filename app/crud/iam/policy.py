from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.models.iam import Policy, Permission
from app.schemas.iam import PolicyCreate, PolicyUpdate
from app.crud.base import CRUDBase

class CRUDPolicy(CRUDBase[Policy, PolicyCreate, PolicyUpdate]):
    def create_with_permissions(self, db: Session, *, obj_in: PolicyCreate) -> Policy:
        # Create policy
        db_obj = Policy(
            name=obj_in.name,
            description=obj_in.description,
            tenant_id=obj_in.tenant_id,
            is_system_policy=obj_in.is_system_policy,
            is_active=obj_in.is_active
        )
        db.add(db_obj)
        db.flush()  # Flush to get the policy_id
        
        # Add permissions if specified
        if obj_in.permission_ids:
            permissions = db.query(Permission).filter(
                Permission.permission_id.in_(obj_in.permission_ids)
            ).all()
            db_obj.permissions = permissions
            
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update_with_permissions(
        self, db: Session, *, db_obj: Policy, obj_in: Union[PolicyUpdate, Dict[str, Any]]
    ) -> Policy:
        # Update policy attributes
        update_data = obj_in.dict(exclude_unset=True) if isinstance(obj_in, PolicyUpdate) else obj_in
        permission_ids = update_data.pop("permission_ids", None)
        
        # Update standard fields
        for field, value in update_data.items():
            setattr(db_obj, field, value)
            
        # Update permissions if specified
        if permission_ids is not None:
            if permission_ids:
                permissions = db.query(Permission).filter(
                    Permission.permission_id.in_(permission_ids)
                ).all()
                db_obj.permissions = permissions
            else:
                db_obj.permissions = []  # Clear all permissions
                
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def get_multi_by_filter(self, db: Session, *, filters: Dict = None, skip: int = 0, limit: int = 100) -> List[Policy]:
        query = db.query(self.model)
        
        if filters:
            if "name" in filters:
                query = query.filter(Policy.name.ilike(f"%{filters['name']}%"))
        
        return query.offset(skip).limit(limit).all()
    
    def count(self, db: Session, *, filters: Dict = None) -> int:
        query = db.query(self.model)
        
        if filters:
            if "name" in filters:
                query = query.filter(Policy.name.ilike(f"%{filters['name']}%"))
        
        return query.count()

policy_crud = CRUDPolicy(Policy)

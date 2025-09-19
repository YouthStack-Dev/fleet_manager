from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.models.iam import Role, Policy
from app.schemas.iam import RoleCreate, RoleUpdate
from app.crud.base import CRUDBase

class CRUDRole(CRUDBase[Role, RoleCreate, RoleUpdate]):

    
    def create_with_policies(self, db: Session, *, obj_in: RoleCreate) -> Role:
        # Create role
        db_obj = Role(
            name=obj_in.name,
            description=obj_in.description,
            tenant_id=obj_in.tenant_id,
            is_system_role=obj_in.is_system_role,
            is_active=obj_in.is_active
        )
        db.add(db_obj)
        db.flush()  # Flush to get the role_id
        
        # Add policies if specified
        if obj_in.policy_ids:
            policies = db.query(Policy).filter(
                Policy.policy_id.in_(obj_in.policy_ids)
            ).all()
            db_obj.policies = policies
            
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update_with_policies(
        self, db: Session, *, db_obj: Role, obj_in: Union[RoleUpdate, Dict[str, Any]]
    ) -> Role:
        # Update role attributes
        update_data = obj_in.dict(exclude_unset=True) if isinstance(obj_in, RoleUpdate) else obj_in
        policy_ids = update_data.pop("policy_ids", None)
        
        # Update standard fields
        for field, value in update_data.items():
            setattr(db_obj, field, value)
            
        # Update policies if specified
        if policy_ids is not None:
            if policy_ids:
                policies = db.query(Policy).filter(
                    Policy.policy_id.in_(policy_ids)
                ).all()
                db_obj.policies = policies
            else:
                db_obj.policies = []  # Clear all policies
                
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def get_multi_by_filter(self, db: Session, *, filters: Dict = None, skip: int = 0, limit: int = 100) -> List[Role]:
        query = db.query(self.model)
        
        if filters:
            if "name" in filters:
                query = query.filter(Role.name.ilike(f"%{filters['name']}%"))
            if "tenant_id" in filters:
                if isinstance(filters["tenant_id"], list):
                    # Handle checking for system roles (tenant_id is None) and tenant-specific roles
                    query = query.filter(Role.tenant_id.in_(filters["tenant_id"]))
                else:
                    query = query.filter(Role.tenant_id == filters["tenant_id"])
            if "is_system_role" in filters:
                query = query.filter(Role.is_system_role == filters["is_system_role"])
        
        return query.offset(skip).limit(limit).all()
    
    def count(self, db: Session, *, filters: Dict = None) -> int:
        query = db.query(self.model)
        
        if filters:
            if "name" in filters:
                query = query.filter(Role.name.ilike(f"%{filters['name']}%"))
            if "tenant_id" in filters:
                if isinstance(filters["tenant_id"], list):
                    # Handle checking for system roles (tenant_id is None) and tenant-specific roles
                    query = query.filter(Role.tenant_id.in_(filters["tenant_id"]))
                else:
                    query = query.filter(Role.tenant_id == filters["tenant_id"])
            if "is_system_role" in filters:
                query = query.filter(Role.is_system_role == filters["is_system_role"])
        
        return query.count()

role_crud = CRUDRole(Role)

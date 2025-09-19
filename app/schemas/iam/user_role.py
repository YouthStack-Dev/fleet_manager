from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from app.schemas.iam.role import RoleResponse

class UserRoleBase(BaseModel):
    user_id: int
    role_id: int
    tenant_id: Optional[str] = None
    is_active: bool = True

class UserRoleCreate(UserRoleBase):
    pass

class UserRoleUpdate(BaseModel):
    is_active: Optional[bool] = None

class UserRoleResponse(UserRoleBase):
    user_role_id: int
    role: RoleResponse
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class UserRolePaginationResponse(BaseModel):
    total: int
    items: List[UserRoleResponse]
    
    model_config = ConfigDict(from_attributes=True)

class UserRoleAssignment(BaseModel):
    user_id: int
    role_ids: List[int]
    tenant_id: Optional[str] = None

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from app.schemas.iam.policy import PolicyResponse

class RoleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    tenant_id: Optional[str] = None
    is_system_role: bool = False
    is_active: bool = True

class RoleCreate(RoleBase):
    policy_ids: List[int] = []

class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    policy_ids: Optional[List[int]] = None

class RoleResponse(RoleBase):
    role_id: int
    policies: List[PolicyResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class RolePaginationResponse(BaseModel):
    total: int
    items: List[RoleResponse]
    
    model_config = ConfigDict(from_attributes=True)

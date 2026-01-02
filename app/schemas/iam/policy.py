from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from app.schemas.iam.permission import PermissionResponse

class PolicyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    tenant_id: Optional[str] = None
    is_active: bool = True

class PolicyCreate(PolicyBase):
    permission_ids: List[int] = []

class PolicyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    permission_ids: Optional[List[int]] = None

class PolicyResponse(PolicyBase):
    policy_id: int
    permissions: List[PermissionResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PolicyPaginationResponse(BaseModel):
    total: int
    items: List[PolicyResponse]
    
    model_config = ConfigDict(from_attributes=True)

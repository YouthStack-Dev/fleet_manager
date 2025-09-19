from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from enum import Enum

class ActionEnum(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    ALL = "*"

class PermissionBase(BaseModel):
    module: str = Field(..., min_length=1, max_length=100)
    action: ActionEnum
    description: Optional[str] = Field(None, max_length=255)
    is_active: bool = True

class PermissionCreate(PermissionBase):
    pass

class PermissionUpdate(BaseModel):
    module: Optional[str] = Field(None, min_length=1, max_length=100)
    action: Optional[ActionEnum] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class PermissionResponse(PermissionBase):
    permission_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PermissionPaginationResponse(BaseModel):
    total: int
    items: List[PermissionResponse]
    
    model_config = ConfigDict(from_attributes=True)

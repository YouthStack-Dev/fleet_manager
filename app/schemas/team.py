from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class TeamBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True

class TeamCreate(TeamBase):
    tenant_id: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Engineering Team",
                "description": "Team handling engineering shift bookings",
                "is_active": True,
                "tenant_id": "tenant_123"
            }
        }
    )

class TeamUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Updated Engineering Team",
                "description": "Updated team description",
                "is_active": True
            }
        }
    )

class TeamResponse(TeamBase):
    team_id: int
    tenant_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TeamPaginationResponse(BaseModel):
    total: int
    items: List[TeamResponse]

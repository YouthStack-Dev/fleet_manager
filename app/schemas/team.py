from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class TeamBase(BaseModel):
    name: str
    description: Optional[str] = None

class TeamCreate(TeamBase):
    tenant_id: Optional[str] = None

class TeamUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class TeamResponse(TeamBase):
    team_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TeamPaginationResponse(BaseModel):
    total: int
    items: List[TeamResponse]

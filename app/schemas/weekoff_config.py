from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class WeekoffConfigBase(BaseModel):
    employee_id: int
    monday: bool = False
    tuesday: bool = False
    wednesday: bool = False
    thursday: bool = False
    friday: bool = False
    saturday: bool = True
    sunday: bool = True

class WeekoffConfigCreate(WeekoffConfigBase):
    pass

class WeekoffConfigUpdate(BaseModel):
    monday: Optional[bool] = None
    tuesday: Optional[bool] = None
    wednesday: Optional[bool] = None
    thursday: Optional[bool] = None
    friday: Optional[bool] = None
    saturday: Optional[bool] = None
    sunday: Optional[bool] = None

class WeekoffConfigResponse(WeekoffConfigBase):
    weekoff_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class WeekoffConfigPaginationResponse(BaseModel):
    total: int
    items: List[WeekoffConfigResponse]

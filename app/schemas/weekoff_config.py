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
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "employee_id": 42,
                "monday": False,
                "tuesday": False,
                "wednesday": False,
                "thursday": False,
                "friday": False,
                "saturday": True,
                "sunday": True
            }
        }
    )

class WeekoffConfigUpdate(BaseModel):
    monday: Optional[bool] = None
    tuesday: Optional[bool] = None
    wednesday: Optional[bool] = None
    thursday: Optional[bool] = None
    friday: Optional[bool] = None
    saturday: Optional[bool] = None
    sunday: Optional[bool] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "monday": True,
                "tuesday": True,
                "saturday": False,
                "sunday": False
            }
        }
    )

class WeekoffConfigResponse(WeekoffConfigBase):
    weekoff_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class WeekoffConfigPaginationResponse(BaseModel):
    total: int
    items: List[WeekoffConfigResponse]

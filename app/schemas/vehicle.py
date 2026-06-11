from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime, date

class VehicleBase(BaseModel):
    vehicle_type_id: int
    contract_id: Optional[int] = None
    vendor_id: Optional[int] = None
    rc_number: str
    driver_id: Optional[int] = None
    rc_expiry_date: Optional[date] = None
    description: Optional[str] = None
    puc_expiry_date: Optional[date] = None
    puc_url: Optional[str] = None
    fitness_expiry_date: Optional[date] = None
    fitness_url: Optional[str] = None
    tax_receipt_date: Optional[date] = None
    tax_receipt_url: Optional[str] = None
    insurance_expiry_date: Optional[date] = None
    insurance_url: Optional[str] = None
    permit_expiry_date: Optional[date] = None
    permit_url: Optional[str] = None
    is_active: bool = True

class VehicleCreate(VehicleBase):
    contract_id: int = Field(..., gt=0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "vehicle_type_id": 1,
                "contract_id": 1,
                "vendor_id": 2,
                "rc_number": "KA05MX1234",
                "driver_id": 10,
                "rc_expiry_date": "2027-12-31",
                "description": "Toyota Innova — white",
                "puc_expiry_date": "2026-06-30",
                "fitness_expiry_date": "2026-09-30",
                "insurance_expiry_date": "2026-12-31",
                "permit_expiry_date": "2027-03-31",
                "is_active": True
            }
        }
    )

class VehicleUpdate(BaseModel):
    vehicle_type_id: Optional[int] = None
    contract_id: Optional[int] = None
    driver_id: Optional[int] = None
    rc_number: Optional[str] = None
    rc_expiry_date: Optional[date] = None
    description: Optional[str] = None
    puc_expiry_date: Optional[date] = None
    puc_url: Optional[str] = None
    fitness_expiry_date: Optional[date] = None
    fitness_url: Optional[str] = None
    tax_receipt_date: Optional[date] = None
    tax_receipt_url: Optional[str] = None
    insurance_expiry_date: Optional[date] = None
    insurance_url: Optional[str] = None
    permit_expiry_date: Optional[date] = None
    permit_url: Optional[str] = None
    is_active: Optional[bool] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "driver_id": 12,
                "contract_id": 1,
                "rc_expiry_date": "2028-06-30",
                "puc_expiry_date": "2027-06-30",
                "insurance_expiry_date": "2027-12-31",
                "is_active": True
            }
        }
    )

class VehicleResponse(VehicleBase):
    vehicle_id: int
    vehicle_type_name: Optional[str] = None
    contract_name: Optional[str] = None
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def model_validate(cls, obj, **kwargs):
        instance = super().model_validate(obj, **kwargs)
        if hasattr(obj, "driver") and obj.driver is not None:
            instance.driver_name = obj.driver.name
            instance.driver_phone = obj.driver.phone
        if hasattr(obj, "contract") and obj.contract is not None:
            instance.contract_name = obj.contract.contract_name
        return instance

class VehiclePaginationResponse(BaseModel):
    total: int
    items: List[VehicleResponse]

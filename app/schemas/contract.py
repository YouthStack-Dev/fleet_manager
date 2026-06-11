from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContractSlabBase(BaseModel):
    min_km: float = Field(..., ge=0, description="Inclusive lower bound in kilometers")
    max_km: Optional[float] = Field(None, gt=0, description="Exclusive upper bound; null means infinity")
    rate: float = Field(..., gt=0, description="Per-kilometer rate for this slab")

    @model_validator(mode="after")
    def validate_range(self):
        if self.max_km is not None and self.max_km <= self.min_km:
            raise ValueError("max_km must be greater than min_km")
        return self


class ContractSlabCreate(ContractSlabBase):
    is_active: bool = True


class ContractSlabUpdate(BaseModel):
    min_km: Optional[float] = Field(None, ge=0)
    max_km: Optional[float] = Field(None, gt=0)
    rate: Optional[float] = Field(None, gt=0)
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def validate_range(self):
        if self.min_km is not None and self.max_km is not None and self.max_km <= self.min_km:
            raise ValueError("max_km must be greater than min_km")
        return self


class ContractSlabResponse(ContractSlabBase):
    slab_id: int
    contract_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContractBase(BaseModel):
    contract_name: str = Field(..., min_length=1, max_length=150)
    vehicle_type_id: int
    cost_center_id: Optional[int] = None

    @field_validator("contract_name")
    def validate_contract_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("contract_name cannot be empty")
        return value


class ContractCreate(ContractBase):
    vendor_id: Optional[int] = None
    is_active: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "vendor_id": 1,
                "vehicle_type_id": 2,
                "contract_name": "Sedan City Contract",
                "cost_center_id": None,
                "is_active": True,
            }
        }
    )


class ContractUpdate(BaseModel):
    contract_name: Optional[str] = Field(None, min_length=1, max_length=150)
    vehicle_type_id: Optional[int] = None
    cost_center_id: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("contract_name")
    def validate_contract_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("contract_name cannot be empty")
        return value


class ContractResponse(ContractBase):
    contract_id: int
    vendor_id: int
    is_active: bool
    vehicle_type_name: Optional[str] = None
    slabs: List[ContractSlabResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def model_validate(cls, obj, **kwargs):
        instance = super().model_validate(obj, **kwargs)
        if hasattr(obj, "vehicle_type") and obj.vehicle_type is not None:
            instance.vehicle_type_name = obj.vehicle_type.name
        return instance


class ContractPaginationResponse(BaseModel):
    total: int
    items: List[ContractResponse]


class CostSlabBreakdown(BaseModel):
    min_km: float
    max_km: Optional[float]
    km_used: float
    rate: float
    cost: float


class CostCalculationResponse(BaseModel):
    route_id: int
    contract_id: int
    contract_name: str
    vehicle_id: int
    vehicle_type_name: Optional[str] = None
    vendor_id: int
    total_distance_km: float
    total_cost: float
    effective_rate: float
    slab_breakdown: List[CostSlabBreakdown]

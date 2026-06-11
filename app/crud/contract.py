from typing import Any, Dict, List, Optional, Union

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.crud.base import CRUDBase
from app.models.contract import Contract, ContractSlab
from app.models.vehicle import Vehicle
from app.models.vehicle_type import VehicleType
from app.schemas.contract import ContractCreate, ContractSlabCreate, ContractSlabUpdate, ContractUpdate
from app.utils.response_utils import ResponseWrapper, handle_db_error


class CRUDContract(CRUDBase[Contract, ContractCreate, ContractUpdate]):
    def get_with_slabs(self, db: Session, *, contract_id: int) -> Optional[Contract]:
        return (
            db.query(Contract)
            .options(joinedload(Contract.slabs), joinedload(Contract.vehicle_type), joinedload(Contract.vendor))
            .filter(Contract.contract_id == contract_id)
            .first()
        )

    def get_by_vendor_and_id(self, db: Session, *, vendor_id: int, contract_id: int) -> Optional[Contract]:
        return (
            db.query(Contract)
            .options(joinedload(Contract.slabs), joinedload(Contract.vehicle_type), joinedload(Contract.vendor))
            .filter(Contract.vendor_id == vendor_id, Contract.contract_id == contract_id)
            .first()
        )

    def get_by_vendor_and_name(self, db: Session, *, vendor_id: int, contract_name: str) -> Optional[Contract]:
        return (
            db.query(Contract)
            .filter(
                Contract.vendor_id == vendor_id,
                Contract.contract_name.ilike(contract_name.strip()),
            )
            .first()
        )

    def get_by_vendor_and_vehicle_type(
        self, db: Session, *, vendor_id: int, vehicle_type_id: int
    ) -> Optional[Contract]:
        return (
            db.query(Contract)
            .filter(Contract.vendor_id == vendor_id, Contract.vehicle_type_id == vehicle_type_id)
            .first()
        )

    def get_by_vendor(
        self,
        db: Session,
        *,
        vendor_id: int,
        active_only: Optional[bool] = None,
        vehicle_type_id: Optional[int] = None,
        search: Optional[str] = None,
    ) -> List[Contract]:
        query = (
            db.query(Contract)
            .options(joinedload(Contract.slabs), joinedload(Contract.vehicle_type), joinedload(Contract.vendor))
            .filter(Contract.vendor_id == vendor_id)
        )

        if active_only is not None:
            query = query.filter(Contract.is_active.is_(active_only))
        if vehicle_type_id is not None:
            query = query.filter(Contract.vehicle_type_id == vehicle_type_id)
        if search:
            query = query.filter(Contract.contract_name.ilike(f"%{search.strip()}%"))

        return query.order_by(Contract.created_at.desc()).all()

    def create_with_vendor(self, db: Session, *, vendor_id: int, obj_in: ContractCreate) -> Contract:
        self._validate_vehicle_type(db, vendor_id=vendor_id, vehicle_type_id=obj_in.vehicle_type_id)

        if self.get_by_vendor_and_name(db, vendor_id=vendor_id, contract_name=obj_in.contract_name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ResponseWrapper.error("Contract name already exists for this vendor", "CONTRACT_NAME_CONFLICT"),
            )

        if self.get_by_vendor_and_vehicle_type(db, vendor_id=vendor_id, vehicle_type_id=obj_in.vehicle_type_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ResponseWrapper.error(
                    "A contract already exists for this vendor and vehicle type",
                    "CONTRACT_VEHICLE_TYPE_CONFLICT",
                ),
            )

        db_obj = Contract(
            vendor_id=vendor_id,
            vehicle_type_id=obj_in.vehicle_type_id,
            cost_center_id=obj_in.cost_center_id,
            contract_name=obj_in.contract_name.strip(),
            is_active=obj_in.is_active,
        )
        db.add(db_obj)
        try:
            db.flush()
        except IntegrityError as e:
            raise handle_db_error(e)
        return db_obj

    def update_with_vendor(
        self, db: Session, *, contract_id: int, obj_in: Union[ContractUpdate, Dict[str, Any]]
    ) -> Contract:
        db_obj = self.get_with_slabs(db, contract_id=contract_id)
        if not db_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Contract not found", "CONTRACT_NOT_FOUND"),
            )

        update_data = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)

        if "contract_name" in update_data:
            new_name = update_data["contract_name"].strip()
            duplicate = self.get_by_vendor_and_name(db, vendor_id=db_obj.vendor_id, contract_name=new_name)
            if duplicate and duplicate.contract_id != db_obj.contract_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=ResponseWrapper.error(
                        "Contract name already exists for this vendor",
                        "CONTRACT_NAME_CONFLICT",
                    ),
                )
            update_data["contract_name"] = new_name

        if "vehicle_type_id" in update_data:
            new_vehicle_type_id = update_data["vehicle_type_id"]
            self._validate_vehicle_type(db, vendor_id=db_obj.vendor_id, vehicle_type_id=new_vehicle_type_id)
            if new_vehicle_type_id != db_obj.vehicle_type_id:
                assigned_count = db.query(Vehicle).filter(Vehicle.contract_id == db_obj.contract_id).count()
                if assigned_count:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ResponseWrapper.error(
                            "Cannot change vehicle type while this contract is assigned to vehicles",
                            "CONTRACT_ASSIGNED_TO_VEHICLES",
                            details={"assigned_vehicle_count": assigned_count},
                        ),
                    )
            duplicate = self.get_by_vendor_and_vehicle_type(
                db, vendor_id=db_obj.vendor_id, vehicle_type_id=new_vehicle_type_id
            )
            if duplicate and duplicate.contract_id != db_obj.contract_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=ResponseWrapper.error(
                        "A contract already exists for this vendor and vehicle type",
                        "CONTRACT_VEHICLE_TYPE_CONFLICT",
                    ),
                )

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        try:
            db.flush()
        except IntegrityError as e:
            raise handle_db_error(e)
        return db_obj

    def soft_delete(self, db: Session, *, contract_id: int, force: bool = False) -> Contract:
        db_obj = self.get_with_slabs(db, contract_id=contract_id)
        if not db_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Contract not found", "CONTRACT_NOT_FOUND"),
            )

        assigned_count = db.query(Vehicle).filter(Vehicle.contract_id == contract_id).count()
        if assigned_count and not force:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    "Contract is assigned to vehicles. Pass force=true to unassign and deactivate it.",
                    "CONTRACT_ASSIGNED_TO_VEHICLES",
                    details={"assigned_vehicle_count": assigned_count},
                ),
            )

        if assigned_count and force:
            db.query(Vehicle).filter(Vehicle.contract_id == contract_id).update({"contract_id": None})

        db_obj.is_active = False
        db.flush()
        return db_obj

    @staticmethod
    def _validate_vehicle_type(db: Session, *, vendor_id: int, vehicle_type_id: int) -> VehicleType:
        vehicle_type = (
            db.query(VehicleType)
            .filter(VehicleType.vehicle_type_id == vehicle_type_id, VehicleType.vendor_id == vendor_id)
            .first()
        )
        if not vehicle_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    "Invalid vehicle_type_id for this vendor",
                    "INVALID_VEHICLE_TYPE",
                ),
            )
        return vehicle_type


class CRUDContractSlab:
    def get_by_contract(self, db: Session, *, contract_id: int, active_only: Optional[bool] = True) -> List[ContractSlab]:
        query = db.query(ContractSlab).filter(ContractSlab.contract_id == contract_id)
        if active_only is not None:
            query = query.filter(ContractSlab.is_active.is_(active_only))
        return query.order_by(ContractSlab.min_km.asc()).all()

    def get_by_id(self, db: Session, *, slab_id: int) -> Optional[ContractSlab]:
        return db.query(ContractSlab).filter(ContractSlab.slab_id == slab_id).first()

    def create(self, db: Session, *, contract_id: int, obj_in: ContractSlabCreate) -> ContractSlab:
        db_obj = ContractSlab(
            contract_id=contract_id,
            min_km=obj_in.min_km,
            max_km=obj_in.max_km,
            rate=obj_in.rate,
            is_active=obj_in.is_active,
        )
        db.add(db_obj)
        db.flush()
        self.validate_active_slab_chain(db, contract_id=contract_id)
        return db_obj

    def update(self, db: Session, *, slab_id: int, obj_in: Union[ContractSlabUpdate, Dict[str, Any]]) -> ContractSlab:
        db_obj = self.get_by_id(db, slab_id=slab_id)
        if not db_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Contract slab not found", "CONTRACT_SLAB_NOT_FOUND"),
            )

        update_data = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)
        proposed_min = update_data.get("min_km", db_obj.min_km)
        proposed_max = update_data.get("max_km", db_obj.max_km)
        if proposed_max is not None and proposed_max <= proposed_min:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error("max_km must be greater than min_km", "INVALID_SLAB_RANGE"),
            )

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.flush()
        self.validate_active_slab_chain(db, contract_id=db_obj.contract_id)
        return db_obj

    def remove(self, db: Session, *, slab_id: int) -> ContractSlab:
        db_obj = self.get_by_id(db, slab_id=slab_id)
        if not db_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Contract slab not found", "CONTRACT_SLAB_NOT_FOUND"),
            )

        contract_id = db_obj.contract_id
        db.delete(db_obj)
        db.flush()
        self.validate_active_slab_chain(db, contract_id=contract_id, allow_empty=True)
        return db_obj

    def validate_active_slab_chain(self, db: Session, *, contract_id: int, allow_empty: bool = False) -> None:
        slabs = self.get_by_contract(db, contract_id=contract_id, active_only=True)
        if not slabs:
            if allow_empty:
                return
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error("At least one active slab is required", "CONTRACT_SLAB_REQUIRED"),
            )

        tolerance = 0.000001
        first = slabs[0]
        if abs(first.min_km - 0) > tolerance:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error("First active slab must start at 0 km", "INVALID_SLAB_CHAIN"),
            )

        for idx, slab in enumerate(slabs):
            if slab.max_km is not None and slab.max_km <= slab.min_km:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error("max_km must be greater than min_km", "INVALID_SLAB_RANGE"),
                )

            if idx == 0:
                continue

            previous = slabs[idx - 1]
            if previous.max_km is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        "No slab can exist after an open-ended slab",
                        "INVALID_SLAB_CHAIN",
                    ),
                )
            if abs(previous.max_km - slab.min_km) > tolerance:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        "Active slabs must be contiguous with no gaps or overlaps",
                        "INVALID_SLAB_CHAIN",
                    ),
                )


contract_crud = CRUDContract(Contract)
contract_slab_crud = CRUDContractSlab()

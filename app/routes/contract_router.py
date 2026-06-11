from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.core.logging_config import get_logger
from app.crud.contract import contract_crud, contract_slab_crud
from app.database.session import get_db
from app.models.contract import Contract
from app.models.vehicle import Vehicle
from app.models.vendor import Vendor
from app.schemas.contract import (
    ContractCreate,
    ContractResponse,
    ContractSlabCreate,
    ContractSlabResponse,
    ContractSlabUpdate,
    ContractUpdate,
    CostCalculationResponse,
)
from app.services.contract_service import calculate_route_cost
from app.utils.audit_helper import log_audit
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from common_utils.auth.permission_checker import PermissionChecker

logger = get_logger(__name__)
router = APIRouter(prefix="/contracts", tags=["contracts"])


def resolve_vendor_scope(db: Session, *, user_data: dict, provided_vendor_id: Optional[int]) -> int:
    user_type = user_data.get("user_type")
    token_vendor_id = user_data.get("vendor_id")

    if user_type in {"admin", "superadmin"}:
        if not provided_vendor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error("vendor_id is required", "VENDOR_ID_REQUIRED"),
            )
        vendor_id = provided_vendor_id
    elif user_type == "vendor":
        if not token_vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("Vendor ID missing in token", "VENDOR_ID_REQUIRED"),
            )
        vendor_id = int(token_vendor_id)
    elif user_type == "employee":
        if not provided_vendor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error("vendor_id is required", "VENDOR_ID_REQUIRED"),
            )
        vendor_id = provided_vendor_id
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error("You don't have permission to access contracts", "FORBIDDEN"),
        )

    validate_vendor_access(db, vendor_id=vendor_id, user_data=user_data)
    return vendor_id


def validate_vendor_access(db: Session, *, vendor_id: int, user_data: dict) -> Vendor:
    vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error("Vendor not found", "VENDOR_NOT_FOUND"),
        )

    if user_data.get("user_type") == "employee":
        token_tenant_id = user_data.get("tenant_id")
        if not token_tenant_id or vendor.tenant_id != token_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("Vendor does not belong to your tenant", "TENANT_FORBIDDEN"),
            )

    return vendor


def get_contract_for_user(db: Session, *, contract_id: int, user_data: dict) -> Contract:
    contract = (
        db.query(Contract)
        .options(joinedload(Contract.vendor), joinedload(Contract.vehicle_type), joinedload(Contract.slabs))
        .filter(Contract.contract_id == contract_id)
        .first()
    )
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error("Contract not found", "CONTRACT_NOT_FOUND"),
        )

    user_type = user_data.get("user_type")
    if user_type == "vendor":
        token_vendor_id = user_data.get("vendor_id")
        if not token_vendor_id or int(contract.vendor_id) != int(token_vendor_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("You cannot access this contract", "FORBIDDEN"),
            )
    elif user_type == "employee":
        token_tenant_id = user_data.get("tenant_id")
        if not token_tenant_id or not contract.vendor or contract.vendor.tenant_id != token_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("You cannot access this contract", "TENANT_FORBIDDEN"),
            )
    elif user_type not in {"admin", "superadmin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ResponseWrapper.error("You cannot access contracts", "FORBIDDEN"),
        )

    return contract


@router.post("/calculate/{route_id}", status_code=status.HTTP_200_OK)
def calculate_completed_route_cost(
    route_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["contract.read"], check_tenant=False)),
):
    try:
        result = calculate_route_cost(db, route_id=route_id, user_data=user_data)
        return ResponseWrapper.success(
            data=CostCalculationResponse(**result),
            message="Route cost calculated successfully",
        )
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("DB error calculating route cost")
        raise handle_db_error(e)
    except Exception as e:
        logger.exception("Unexpected error calculating route cost")
        raise handle_http_error(e)


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_contract(
    payload: ContractCreate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["contract.create"], check_tenant=False)),
):
    try:
        vendor_id = resolve_vendor_scope(db, user_data=user_data, provided_vendor_id=payload.vendor_id)
        db_obj = contract_crud.create_with_vendor(db, vendor_id=vendor_id, obj_in=payload)
        db.commit()
        db.refresh(db_obj)

        try:
            log_audit(
                db=db,
                tenant_id=db_obj.vendor.tenant_id if db_obj.vendor else None,
                module="contract",
                action="CREATE",
                user_data=user_data,
                description=f"Created contract '{db_obj.contract_name}' for vendor {vendor_id}",
                new_values={
                    "contract_id": db_obj.contract_id,
                    "vendor_id": db_obj.vendor_id,
                    "vehicle_type_id": db_obj.vehicle_type_id,
                    "contract_name": db_obj.contract_name,
                    "is_active": db_obj.is_active,
                },
                request=request,
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for contract creation: {audit_error}")

        return ResponseWrapper.success(
            data={"contract": ContractResponse.model_validate(db_obj, from_attributes=True)},
            message="Contract created successfully",
        )
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("DB error creating contract")
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error creating contract")
        raise handle_http_error(e)


@router.get("/", status_code=status.HTTP_200_OK)
def list_contracts(
    vendor_id: Optional[int] = Query(None),
    vehicle_type_id: Optional[int] = Query(None),
    active_only: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["contract.read"], check_tenant=False)),
):
    try:
        vendor_id = resolve_vendor_scope(db, user_data=user_data, provided_vendor_id=vendor_id)
        contracts = contract_crud.get_by_vendor(
            db,
            vendor_id=vendor_id,
            active_only=active_only,
            vehicle_type_id=vehicle_type_id,
            search=search,
        )
        return ResponseWrapper.success(
            data={
                "total": len(contracts),
                "items": [ContractResponse.model_validate(obj, from_attributes=True) for obj in contracts],
            },
            message="Contracts fetched successfully",
        )
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("DB error listing contracts")
        raise handle_db_error(e)
    except Exception as e:
        logger.exception("Unexpected error listing contracts")
        raise handle_http_error(e)


@router.get("/vendor/{vendor_id}/contract-summary", status_code=status.HTTP_200_OK)
def get_vendor_vehicle_contract_summary(
    vendor_id: int,
    active_only: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["contract.read"], check_tenant=False)),
):
    """
    Lightweight vehicle-contract list for UI screens.

    Returns vehicle number/type and assigned contract id/name for a vendor.
    """
    try:
        user_type = user_data.get("user_type")
        token_vendor_id = user_data.get("vendor_id")
        token_tenant_id = user_data.get("tenant_id")

        vendor = db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
        if not vendor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Vendor not found", "VENDOR_NOT_FOUND"),
            )

        if user_type == "vendor":
            if not token_vendor_id or int(token_vendor_id) != int(vendor_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error("You cannot access this vendor's contracts", "FORBIDDEN"),
                )
        elif user_type == "employee":
            if not token_tenant_id or vendor.tenant_id != token_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error("Vendor does not belong to your tenant", "TENANT_FORBIDDEN"),
                )
        elif user_type not in {"admin", "superadmin"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error("You don't have permission to access contracts", "FORBIDDEN"),
            )

        query = (
            db.query(Vehicle)
            .options(joinedload(Vehicle.vehicle_type), joinedload(Vehicle.contract), joinedload(Vehicle.driver))
            .filter(Vehicle.vendor_id == vendor_id)
        )
        if active_only is not None:
            query = query.filter(Vehicle.is_active.is_(active_only))

        vehicles = query.order_by(Vehicle.rc_number.asc()).all()
        items = []
        for vehicle in vehicles:
            vehicle_type_name = vehicle.vehicle_type.name if vehicle.vehicle_type else None
            contract_name = vehicle.contract.contract_name if vehicle.contract else None
            items.append(
                {
                    "vehicle_id": vehicle.vehicle_id,
                    "vehicle_label": f"{vehicle_type_name or 'Vehicle'} - {vehicle.rc_number}",
                    "rc_number": vehicle.rc_number,
                    "vehicle_type_id": vehicle.vehicle_type_id,
                    "vehicle_type_name": vehicle_type_name,
                    "contract_id": vehicle.contract_id,
                    "contract_name": contract_name,
                    "driver_id": vehicle.driver_id,
                    "driver_name": vehicle.driver.name if vehicle.driver else None,
                    "is_active": vehicle.is_active,
                }
            )

        return ResponseWrapper.success(
            data={"vendor_id": vendor_id, "total": len(items), "items": items},
            message="Vehicle contract summary fetched successfully",
        )
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("DB error fetching vehicle contract summary")
        raise handle_db_error(e)
    except Exception as e:
        logger.exception("Unexpected error fetching vehicle contract summary")
        raise handle_http_error(e)


@router.get("/{contract_id}", status_code=status.HTTP_200_OK)
def get_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["contract.read"], check_tenant=False)),
):
    try:
        contract = get_contract_for_user(db, contract_id=contract_id, user_data=user_data)
        return ResponseWrapper.success(
            data={"contract": ContractResponse.model_validate(contract, from_attributes=True)},
            message="Contract fetched successfully",
        )
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("DB error fetching contract")
        raise handle_db_error(e)
    except Exception as e:
        logger.exception("Unexpected error fetching contract")
        raise handle_http_error(e)


@router.put("/{contract_id}", status_code=status.HTTP_200_OK)
def update_contract(
    contract_id: int,
    payload: ContractUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["contract.update"], check_tenant=False)),
):
    try:
        contract = get_contract_for_user(db, contract_id=contract_id, user_data=user_data)
        update_data = payload.model_dump(exclude_unset=True)
        old_values = {field: getattr(contract, field, None) for field in update_data.keys()}

        updated = contract_crud.update_with_vendor(db, contract_id=contract_id, obj_in=payload)
        db.commit()
        db.refresh(updated)

        try:
            new_values = {field: getattr(updated, field, None) for field in update_data.keys()}
            log_audit(
                db=db,
                tenant_id=updated.vendor.tenant_id if updated.vendor else None,
                module="contract",
                action="UPDATE",
                user_data=user_data,
                description=f"Updated contract '{updated.contract_name}'",
                new_values={"old": old_values, "new": new_values},
                request=request,
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for contract update: {audit_error}")

        return ResponseWrapper.success(
            data={"contract": ContractResponse.model_validate(updated, from_attributes=True)},
            message="Contract updated successfully",
        )
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("DB error updating contract")
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error updating contract")
        raise handle_http_error(e)


@router.patch("/{contract_id}/toggle-status", status_code=status.HTTP_200_OK)
def toggle_contract_status(
    contract_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["contract.update"], check_tenant=False)),
):
    try:
        contract = get_contract_for_user(db, contract_id=contract_id, user_data=user_data)
        old_status = contract.is_active
        contract.is_active = not contract.is_active
        db.commit()
        db.refresh(contract)

        try:
            log_audit(
                db=db,
                tenant_id=contract.vendor.tenant_id if contract.vendor else None,
                module="contract",
                action="UPDATE",
                user_data=user_data,
                description=f"Toggled contract '{contract.contract_name}' status",
                new_values={"old_status": old_status, "new_status": contract.is_active},
                request=request,
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for contract status toggle: {audit_error}")

        status_text = "activated" if contract.is_active else "deactivated"
        return ResponseWrapper.success(
            data={"contract": ContractResponse.model_validate(contract, from_attributes=True)},
            message=f"Contract {status_text} successfully",
        )
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("DB error toggling contract status")
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error toggling contract status")
        raise handle_http_error(e)


@router.delete("/{contract_id}", status_code=status.HTTP_200_OK)
def delete_contract(
    contract_id: int,
    request: Request,
    force: bool = Query(False),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["contract.delete"], check_tenant=False)),
):
    try:
        contract = get_contract_for_user(db, contract_id=contract_id, user_data=user_data)
        deleted = contract_crud.soft_delete(db, contract_id=contract.contract_id, force=force)
        db.commit()
        db.refresh(deleted)

        try:
            log_audit(
                db=db,
                tenant_id=deleted.vendor.tenant_id if deleted.vendor else None,
                module="contract",
                action="DELETE",
                user_data=user_data,
                description=f"Deactivated contract '{deleted.contract_name}'",
                new_values={"contract_id": deleted.contract_id, "is_active": deleted.is_active, "force": force},
                request=request,
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for contract delete: {audit_error}")

        return ResponseWrapper.success(message="Contract deactivated successfully")
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("DB error deleting contract")
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error deleting contract")
        raise handle_http_error(e)


@router.post("/{contract_id}/slabs", status_code=status.HTTP_201_CREATED)
def create_contract_slab(
    contract_id: int,
    payload: ContractSlabCreate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["contract.update"], check_tenant=False)),
):
    try:
        contract = get_contract_for_user(db, contract_id=contract_id, user_data=user_data)
        slab = contract_slab_crud.create(db, contract_id=contract.contract_id, obj_in=payload)
        db.commit()
        db.refresh(slab)

        try:
            log_audit(
                db=db,
                tenant_id=contract.vendor.tenant_id if contract.vendor else None,
                module="contract",
                action="UPDATE",
                user_data=user_data,
                description=f"Added slab to contract '{contract.contract_name}'",
                new_values={
                    "slab_id": slab.slab_id,
                    "contract_id": slab.contract_id,
                    "min_km": slab.min_km,
                    "max_km": slab.max_km,
                    "rate": slab.rate,
                },
                request=request,
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for slab creation: {audit_error}")

        return ResponseWrapper.success(
            data={"slab": ContractSlabResponse.model_validate(slab, from_attributes=True)},
            message="Contract slab created successfully",
        )
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("DB error creating contract slab")
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error creating contract slab")
        raise handle_http_error(e)


@router.put("/{contract_id}/slabs/{slab_id}", status_code=status.HTTP_200_OK)
def update_contract_slab(
    contract_id: int,
    slab_id: int,
    payload: ContractSlabUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["contract.update"], check_tenant=False)),
):
    try:
        contract = get_contract_for_user(db, contract_id=contract_id, user_data=user_data)
        slab = contract_slab_crud.get_by_id(db, slab_id=slab_id)
        if not slab or slab.contract_id != contract.contract_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Contract slab not found", "CONTRACT_SLAB_NOT_FOUND"),
            )

        old_values = {
            field: getattr(slab, field, None)
            for field in payload.model_dump(exclude_unset=True).keys()
        }
        updated = contract_slab_crud.update(db, slab_id=slab_id, obj_in=payload)
        db.commit()
        db.refresh(updated)

        try:
            new_values = {
                field: getattr(updated, field, None)
                for field in payload.model_dump(exclude_unset=True).keys()
            }
            log_audit(
                db=db,
                tenant_id=contract.vendor.tenant_id if contract.vendor else None,
                module="contract",
                action="UPDATE",
                user_data=user_data,
                description=f"Updated slab {slab_id} for contract '{contract.contract_name}'",
                new_values={"old": old_values, "new": new_values},
                request=request,
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for slab update: {audit_error}")

        return ResponseWrapper.success(
            data={"slab": ContractSlabResponse.model_validate(updated, from_attributes=True)},
            message="Contract slab updated successfully",
        )
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("DB error updating contract slab")
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error updating contract slab")
        raise handle_http_error(e)


@router.delete("/{contract_id}/slabs/{slab_id}", status_code=status.HTTP_200_OK)
def delete_contract_slab(
    contract_id: int,
    slab_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["contract.update"], check_tenant=False)),
):
    try:
        contract = get_contract_for_user(db, contract_id=contract_id, user_data=user_data)
        slab = contract_slab_crud.get_by_id(db, slab_id=slab_id)
        if not slab or slab.contract_id != contract.contract_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error("Contract slab not found", "CONTRACT_SLAB_NOT_FOUND"),
            )

        deleted = contract_slab_crud.remove(db, slab_id=slab_id)
        db.commit()

        try:
            log_audit(
                db=db,
                tenant_id=contract.vendor.tenant_id if contract.vendor else None,
                module="contract",
                action="UPDATE",
                user_data=user_data,
                description=f"Deleted slab {slab_id} from contract '{contract.contract_name}'",
                new_values={
                    "slab_id": deleted.slab_id,
                    "contract_id": deleted.contract_id,
                    "min_km": deleted.min_km,
                    "max_km": deleted.max_km,
                    "rate": deleted.rate,
                },
                request=request,
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for slab delete: {audit_error}")

        return ResponseWrapper.success(message="Contract slab deleted successfully")
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("DB error deleting contract slab")
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error deleting contract slab")
        raise handle_http_error(e)

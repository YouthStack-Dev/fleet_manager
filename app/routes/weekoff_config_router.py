from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database.session import get_db
from app.crud.weekoff import weekoff_crud
from app.schemas.weekoff_config import WeekoffConfigUpdate, WeekoffConfigResponse
from common_utils.auth.permission_checker import PermissionChecker
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from sqlalchemy.exc import SQLAlchemyError
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/weekoff-configs", tags=["weekoff configs"])


@router.get("/{employee_id}")
def get_weekoff_by_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["weekoff-config.read"], check_tenant=True)),
):
    """
    Fetch weekoff config for an employee.
    - employee → only within their tenant
    - admin → can access any tenant
    """
    try:
        tenant_id = user_data.get("tenant_id")
        user_type = user_data.get("user_type")

        db_obj = weekoff_crud.ensure_weekoff_config(db, employee_id=employee_id)

        if user_type == "employee" and db_obj.employee.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You cannot view weekoff config outside your tenant",
                    error_code="TENANT_FORBIDDEN",
                ),
            )

        return ResponseWrapper.success(
            data={"weekoff_config": WeekoffConfigResponse.model_validate(db_obj, from_attributes=True)},
            message="Weekoff config fetched successfully"
        )

    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error fetching weekoff config for employee {employee_id}: {e}")
        raise handle_http_error(e)


@router.put("/{employee_id}", response_model=WeekoffConfigResponse)
def update_weekoff_by_employee(
    employee_id: int,
    update_in: WeekoffConfigUpdate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["weekoff-config.update"], check_tenant=True)),
):
    """
    Update weekoff config for an employee.
    """
    try:
        tenant_id = user_data.get("tenant_id")
        user_type = user_data.get("user_type")

        db_obj = weekoff_crud.ensure_weekoff_config(db, employee_id=employee_id)

        if user_type == "employee" and db_obj.employee.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You cannot update weekoff config outside your tenant",
                    error_code="TENANT_FORBIDDEN",
                ),
            )

        db_obj = weekoff_crud.update_by_employee(db, employee_id=employee_id, obj_in=update_in)
        db.commit()
        db.refresh(db_obj)

        return ResponseWrapper.success(
            data={"weekoff_config": WeekoffConfigResponse.model_validate(db_obj, from_attributes=True)},
            message="Weekoff config updated successfully"
        )

    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error updating weekoff config for employee {employee_id}: {e}")
        raise handle_http_error(e)


@router.put("/team/{team_id}", response_model=List[WeekoffConfigResponse])
def update_weekoff_by_team(
    team_id: int,
    update_in: WeekoffConfigUpdate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["weekoff-config.update"], check_tenant=True)),
):
    """
    Bulk update weekoff configs for a team.
    """
    try:
        tenant_id = user_data.get("tenant_id")
        user_type = user_data.get("user_type")

        db_objs = weekoff_crud.update_by_team(db, team_id=team_id, obj_in=update_in)

        if user_type == "employee":
            db_objs = [obj for obj in db_objs if obj.employee.tenant_id == tenant_id]

        db.commit()
        return [
            WeekoffConfigResponse.model_validate(obj, from_attributes=True)
            for obj in db_objs
        ]

    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except Exception as e:
        logger.exception(f"Unexpected error updating weekoff config for team {team_id}: {e}")
        raise handle_http_error(e)


@router.put("/tenant/{tenant_id}", response_model=List[WeekoffConfigResponse])
def update_weekoff_by_tenant(
    tenant_id: str,
    update_in: WeekoffConfigUpdate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["weekoff-config.update"], check_tenant=True)),
):
    """
    Bulk update weekoff configs for a tenant.
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        if user_type == "employee" and tenant_id != token_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You cannot update weekoff config outside your tenant",
                    error_code="TENANT_FORBIDDEN",
                ),
            )

        db_objs = weekoff_crud.update_by_tenant(db, tenant_id=tenant_id, obj_in=update_in)
        db.commit()

        return [
            WeekoffConfigResponse.model_validate(obj, from_attributes=True)
            for obj in db_objs
        ]

    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except Exception as e:
        logger.exception(f"Unexpected error updating weekoff config for tenant {tenant_id}: {e}")
        raise handle_http_error(e)


@router.get("/team/{team_id}", response_model=List[WeekoffConfigResponse])
def get_weekoffs_by_team(
    team_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["weekoff-config.read"], check_tenant=True)),
):
    """
    Fetch weekoff configs for all employees in a team.
    """
    try:
        tenant_id = user_data.get("tenant_id")
        user_type = user_data.get("user_type")

        db_objs = weekoff_crud.get_by_team(db, team_id=team_id)
        if user_type == "employee":
            db_objs = [obj for obj in db_objs if obj.employee.tenant_id == tenant_id]

        return [
            WeekoffConfigResponse.model_validate(obj, from_attributes=True)
            for obj in db_objs
        ]

    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except Exception as e:
        logger.exception(f"Unexpected error fetching weekoff configs for team {team_id}: {e}")
        raise handle_http_error(e)


@router.get("/tenant/{tenant_id}", response_model=List[WeekoffConfigResponse])
def get_weekoffs_by_tenant(
    tenant_id: str,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["weekoff-config.read"], check_tenant=True)),
):
    """
    Fetch weekoff configs for all employees in a tenant.
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        if user_type == "employee" and tenant_id != token_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You cannot view weekoff config outside your tenant",
                    error_code="TENANT_FORBIDDEN",
                ),
            )

        db_objs = weekoff_crud.get_by_tenant(db, tenant_id=tenant_id)

        return [
            WeekoffConfigResponse.model_validate(obj, from_attributes=True)
            for obj in db_objs
        ]

    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except Exception as e:
        logger.exception(f"Unexpected error fetching weekoff configs for tenant {tenant_id}: {e}")
        raise handle_http_error(e)

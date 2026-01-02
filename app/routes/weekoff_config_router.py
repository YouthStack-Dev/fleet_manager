from app.models.employee import Employee
from app.models.team import Team
from app.models.weekoff_config import WeekoffConfig
from app.utils.pagination import paginate_query
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from app.crud.team import team_crud
from app.database.session import get_db
from app.crud.weekoff import weekoff_crud
from app.crud.tenant import tenant_crud
from app.schemas.weekoff_config import WeekoffConfigUpdate, WeekoffConfigResponse
from common_utils.auth.permission_checker import PermissionChecker
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from sqlalchemy.exc import SQLAlchemyError
from app.core.logging_config import get_logger
from app.utils.audit_helper import log_audit

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

@router.get("/team/{team_id}", response_model=dict, status_code=status.HTTP_200_OK)
def get_weekoffs_by_team(
    team_id: int,
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["weekoff-config.read"])),
):
    """
    Fetch weekoff configs for all employees in a team.
    - employee → only within their tenant
    - admin → can access any tenant
    Paginated, filtered by is_active.
    Ensures every employee has a weekoff config.
    """
    try:
        tenant_id = user_data.get("tenant_id")
        user_type = user_data.get("user_type")

        # Check team exists
        team = team_crud.get_by_id(db, team_id=team_id)
        if not team:
            logger.warning(f"Team {team_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Team {team_id} not found",
                    error_code="TEAM_NOT_FOUND",
                ),
            )

        # Tenant enforcement for employees
        if user_type == "employee" and team.tenant_id != tenant_id:
            logger.warning(
                f"Employee user cannot access weekoff configs outside their tenant "
                f"(team_id={team_id}, user_tenant={tenant_id})"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You cannot access weekoff configs outside your tenant",
                    error_code="TENANT_FORBIDDEN",
                ),
            )

        # Query employees in team
        query = db.query(Employee).filter(Employee.team_id == team_id)
        if user_type == "employee":
            query = query.filter(Employee.tenant_id == tenant_id)
        if is_active is not None:
            query = query.filter(Employee.is_active == is_active)

        total, employees = paginate_query(query, skip, limit)

        # Prepare weekoff configs
        configs_response = []
        for emp in employees:
            try:
                config = weekoff_crud.ensure_weekoff_config(db, employee_id=emp.employee_id)
                db.flush()  # flush changes without committing yet
            except HTTPException:
                logger.warning(f"Skipping weekoff config for employee {emp.employee_id} (not found)")
                continue

            configs_response.append(
                WeekoffConfigResponse.model_validate(config, from_attributes=True).model_dump()
            )

        db.commit()  # commit all default weekoff configs at once

        return ResponseWrapper.success(
            data={"total": total, "items": configs_response},
            message=f"Weekoff configs fetched for team {team_id}"
        )

    except SQLAlchemyError as e:
        logger.exception(f"DB error while fetching weekoff configs for team {team_id}: {e}")
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while fetching weekoff configs for team {team_id}: {e}")
        raise handle_http_error(e)

@router.get("/tenant/", response_model=dict, status_code=status.HTTP_200_OK)
def get_weekoffs_by_tenant(
    tenant_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["weekoff-config.read"])),
):
    """
    Fetch weekoff configs for all employees in a tenant.
    - employee → only within their tenant
    - admin → can access any tenant
    Paginated, filtered by is_active.
    Ensures every employee has a weekoff config.
    """
    try:
        logger.info("Starting get_weekoffs_by_tenant")
        logger.debug(f"user_data: {user_data}, tenant_id param: {tenant_id}, skip: {skip}, limit: {limit}, is_active: {is_active}")

        user_type = user_data.get("user_type")
        logger.info(f"User type: {user_type}")

        # 🚫 Vendors/Drivers forbidden
        if user_type in {"vendor", "driver"}:
            logger.warning("Vendor/Driver attempted to fetch weekoff configs")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to view employees",
                    error_code="FORBIDDEN",
                ),
            )

        # Employee tenant enforcement
        if user_type == "employee":
            tenant_id = user_data.get("tenant_id")
            logger.info(f"Employee tenant enforced: {tenant_id}")
            if not tenant_id:
                logger.error("Tenant ID missing in token for employee")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
        elif user_type == "admin":
            if not tenant_id:
                logger.error("Tenant ID missing for admin request")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Tenant ID is required for admin",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
            logger.info(f"Admin requested tenant: {tenant_id}")
            # Ensure tenant exists
        if not tenant_crud.get_by_id(db, tenant_id=tenant_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND",
                ),
            )
        # Query employees in tenant
        logger.info(f"Querying employees in tenant {tenant_id}")
        query = db.query(Employee).filter(Employee.tenant_id == tenant_id)
        if is_active is not None:
            query = query.filter(Employee.is_active == is_active)
            logger.info(f"Filtering employees by is_active={is_active}")

        total, employees = paginate_query(query, skip, limit)
        logger.info(f"Fetched {len(employees)} employees (total: {total}) for tenant {tenant_id}")

        # Prepare weekoff configs
        configs_response = []
        for emp in employees:
            logger.debug(f"Processing employee_id={emp.employee_id}, name={emp.name}")
            try:
                config = weekoff_crud.ensure_weekoff_config(db, employee_id=emp.employee_id)
                db.flush()  # flush changes without committing yet
                logger.debug(f"Weekoff config ensured for employee {emp.employee_id}")
            except HTTPException:
                logger.warning(f"Skipping weekoff config for employee {emp.employee_id} (not found)")
                continue

            configs_response.append(
                WeekoffConfigResponse.model_validate(config, from_attributes=True).model_dump()
            )

        db.commit()  # commit all default weekoff configs at once
        logger.info(f"Committed weekoff configs for tenant {tenant_id}")

        return ResponseWrapper.success(
            data={"total": total, "items": configs_response},
            message=f"Weekoff configs fetched for tenant {tenant_id}"
        )

    except SQLAlchemyError as e:
        logger.exception(f"DB error while fetching weekoff configs for tenant {tenant_id}: {e}")
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while fetching weekoff configs for tenant {tenant_id}: {e}")
        raise handle_http_error(e)


@router.put("/{employee_id}", response_model=dict, status_code=status.HTTP_200_OK)
def update_weekoff_by_employee(
    employee_id: int,
    update_in: WeekoffConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["weekoff-config.update"])),
):
    """
    Update weekoff config for an employee.
    - employee → only within their tenant
    - admin → can access any tenant
    Includes validation and detailed logs.
    """
    try:
        logger.info(f"Starting weekoff update for employee_id={employee_id}")
        logger.debug(f"Payload received: {update_in.model_dump(exclude_unset=True)}")

        tenant_id = user_data.get("tenant_id")
        user_type = user_data.get("user_type")
        logger.info(f"Requester user_type={user_type}, tenant_id={tenant_id}")

        # 🚫 Vendors/Drivers forbidden
        if user_type in {"vendor", "driver"}:
            logger.warning("Vendor/Driver attempted to fetch weekoff configs")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to view employees",
                    error_code="FORBIDDEN",
                ),
            )

        # Ensure employee exists
        employee = db.query(Employee).filter(Employee.employee_id == employee_id).first()
        if not employee:
            logger.warning(f"Employee {employee_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Employee {employee_id} not found",
                    error_code="EMPLOYEE_NOT_FOUND",
                ),
            )
        logger.info(f"Employee {employee_id} found (tenant_id={employee.tenant_id}, is_active={employee.is_active})")

        # Tenant enforcement
        if user_type == "employee" and employee.tenant_id != tenant_id:
            logger.warning(
                f"Employee user cannot update weekoff outside their tenant "
                f"(employee_id={employee_id}, employee_tenant={employee.tenant_id}, user_tenant={tenant_id})"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You cannot update weekoff config outside your tenant",
                    error_code="TENANT_FORBIDDEN",
                ),
            )

        # Ensure config exists or create default
        db_obj = weekoff_crud.ensure_weekoff_config(db, employee_id=employee_id)
        logger.debug(f"Existing weekoff config found for employee {employee_id}: weekoff_id={db_obj.weekoff_id}")

        # 🔍 Capture old values before update
        old_values = {
            "monday": db_obj.monday,
            "tuesday": db_obj.tuesday,
            "wednesday": db_obj.wednesday,
            "thursday": db_obj.thursday,
            "friday": db_obj.friday,
            "saturday": db_obj.saturday,
            "sunday": db_obj.sunday
        }

        # Update via CRUD
        db_obj = weekoff_crud.update_by_employee(db, employee_id=employee_id, obj_in=update_in)
        logger.info(f"Weekoff config updated for employee {employee_id}: {update_in.model_dump(exclude_unset=True)}")

        db.commit()
        db.refresh(db_obj)
        logger.info(f"Committed weekoff update for employee {employee_id}")

        # 🔍 Capture new values after update
        new_values = {
            "monday": db_obj.monday,
            "tuesday": db_obj.tuesday,
            "wednesday": db_obj.wednesday,
            "thursday": db_obj.thursday,
            "friday": db_obj.friday,
            "saturday": db_obj.saturday,
            "sunday": db_obj.sunday
        }

        # 🔍 Audit Log: Weekoff Config Update
        try:
            log_audit(
                db=db,
                tenant_id=employee.tenant_id,
                module="weekoff_config",
                action="UPDATE",
                user_data=user_data,
                description=f"Updated weekoff config for employee '{employee.name}' (ID: {employee_id})",
                new_values={"old": old_values, "new": new_values},
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for weekoff update: {str(audit_error)}")

        return ResponseWrapper.success(
            data={"weekoff_config": WeekoffConfigResponse.model_validate(db_obj, from_attributes=True)},
            message=f"Weekoff config updated successfully for employee {employee_id}"
        )

    except SQLAlchemyError as e:
        logger.exception(f"DB error while updating weekoff config for employee {employee_id}: {e}")
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error updating weekoff config for employee {employee_id}: {e}")
        raise handle_http_error(e)

@router.put("/team/{team_id}", response_model=dict, status_code=status.HTTP_200_OK)
def update_weekoff_by_team(
    team_id: int,
    update_in: WeekoffConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["weekoff-config.update"])),
):
    """
    Bulk update weekoff configs for all employees under a team.
    - employee → only within their tenant
    - admin → can update across tenants
    Includes validation, tenant enforcement, and detailed logs.
    """
    try:
        logger.info(f"Starting bulk weekoff update for team_id={team_id}")
        logger.debug(f"Payload received: {update_in.model_dump(exclude_unset=True)}")

        tenant_id = user_data.get("tenant_id")
        user_type = user_data.get("user_type")
        logger.info(f"Requester user_type={user_type}, tenant_id={tenant_id}")

        # 🚫 Vendors/Drivers forbidden
        if user_type in {"vendor", "driver"}:
            logger.warning("Vendor/Driver attempted to update weekoff configs")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to update weekoff configs",
                    error_code="FORBIDDEN",
                ),
            )

        # ✅ Ensure team exists
        team = db.query(Team).filter(Team.team_id == team_id).first()
        if not team:
            logger.warning(f"Team {team_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Team {team_id} not found",
                    error_code="TEAM_NOT_FOUND",
                ),
            )
        logger.info(f"Team {team_id} found (tenant_id={team.tenant_id})")

        # 🔒 Tenant enforcement
        if user_type == "employee" and team.tenant_id != tenant_id:
            logger.warning(
                f"Employee user cannot update weekoff outside their tenant "
                f"(team_id={team_id}, team_tenant={team.tenant_id}, user_tenant={tenant_id})"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You cannot update weekoff config outside your tenant",
                    error_code="TENANT_FORBIDDEN",
                ),
            )

        # ✅ Bulk update via CRUD
        db_objs = weekoff_crud.update_by_team(db, team_id=team_id, obj_in=update_in)
        logger.info(f"Weekoff configs updated for {len(db_objs)} employees in team {team_id}")

        db.commit()
        for obj in db_objs:
            db.refresh(obj)
        logger.info(f"Committed bulk weekoff update for team {team_id}")

        # 🔍 Audit Log: Team Weekoff Config Update
        try:
            log_audit(
                db=db,
                tenant_id=team.tenant_id,
                module="weekoff_config",
                action="UPDATE",
                user_data=user_data,
                description=f"Bulk updated weekoff configs for team '{team.team_name}' (ID: {team_id}) - {len(db_objs)} employees affected",
                new_values={
                    "team_id": team_id,
                    "team_name": team.team_name,
                    "employees_updated": len(db_objs),
                    "changes": update_in.model_dump(exclude_unset=True)
                },
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for team weekoff update: {str(audit_error)}")

        return ResponseWrapper.success(
            data={
                "weekoff_configs": [
                    WeekoffConfigResponse.model_validate(obj, from_attributes=True)
                    for obj in db_objs
                ]
            },
            message=f"Weekoff configs updated successfully for team {team_id} ({len(db_objs)} employees)",
        )

    except SQLAlchemyError as e:
        logger.exception(f"DB error while updating weekoff config for team {team_id}: {e}")
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error updating weekoff config for team {team_id}: {e}")
        raise handle_http_error(e)



@router.put("/tenant/{tenant_id}", response_model=dict, status_code=status.HTTP_200_OK)
def update_weekoff_by_tenant(
    tenant_id: Optional[str],
    update_in: WeekoffConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["weekoff-config.update"])),
):
    """
    Bulk update weekoff configs for all employees under a tenant.
    - employee → only within their tenant
    - admin → can update across tenants
    Includes validation, tenant enforcement, and detailed logs.
    """
    try:
        logger.info(f"Starting bulk weekoff update for tenant_id={tenant_id}")
        logger.debug(f"Payload received: {update_in.model_dump(exclude_unset=True)}")

        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")
        logger.info(f"Requester user_type={user_type}, token_tenant_id={token_tenant_id}")

        # 🚫 Vendors/Drivers forbidden
        if user_type in {"vendor", "driver"}:
            logger.warning("Vendor/Driver attempted to update weekoff configs")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to update weekoff configs",
                    error_code="FORBIDDEN",
                ),
            )

        # 🔒 Tenant enforcement for employee role
        if user_type == "employee" and tenant_id != token_tenant_id:
            logger.warning(
                f"Employee user teanant_id enforced from token, ignoring path param "
                f"(tenant_id={tenant_id}, token_tenant_id={token_tenant_id})"
            )
            tenant_id = token_tenant_id
        # ✅ Ensure tenant exists
        tenant = tenant_crud.get_by_id(db, tenant_id=tenant_id)
        if not tenant:
            logger.warning(f"Tenant {tenant_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Tenant {tenant_id} not found",
                    error_code="TENANT_NOT_FOUND",
                ),
            )
        logger.info(f"Tenant {tenant_id} found")

        # ✅ Bulk update via CRUD
        db_objs = weekoff_crud.update_by_tenant(db, tenant_id=tenant_id, obj_in=update_in)
        logger.info(f"Weekoff configs updated for {len(db_objs)} employees in tenant {tenant_id}")

        db.commit()
        for obj in db_objs:
            db.refresh(obj)
        logger.info(f"Committed bulk weekoff update for tenant {tenant_id}")

        # 🔍 Audit Log: Tenant Weekoff Config Update
        try:
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="weekoff_config",
                action="UPDATE",
                user_data=user_data,
                description=f"Bulk updated weekoff configs for tenant '{tenant.company_name}' (ID: {tenant_id}) - {len(db_objs)} employees affected",
                new_values={
                    "tenant_id": tenant_id,
                    "company_name": tenant.company_name,
                    "employees_updated": len(db_objs),
                    "changes": update_in.model_dump(exclude_unset=True)
                },
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for tenant weekoff update: {str(audit_error)}")

        return ResponseWrapper.success(
            data={
                "weekoff_configs": [
                    WeekoffConfigResponse.model_validate(obj, from_attributes=True)
                    for obj in db_objs
                ]
            },
            message=f"Weekoff configs updated successfully for tenant {tenant_id} ({len(db_objs)} employees)",
        )

    except SQLAlchemyError as e:
        logger.exception(f"DB error while updating weekoff configs for tenant {tenant_id}: {e}")
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error updating weekoff config for tenant {tenant_id}: {e}")
        raise handle_http_error(e)


from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Query, Request
from app.core.email_service import get_email_service
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.models.employee import Employee
from app.schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeResponse, EmployeePaginationResponse
from app.utils.pagination import paginate_query
from common_utils.auth.permission_checker import PermissionChecker
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from common_utils.auth.utils import hash_password
from app.crud.employee import employee_crud
from app.crud.team import team_crud
from app.crud.tenant import tenant_crud
from sqlalchemy.exc import SQLAlchemyError
from app.core.logging_config import get_logger
from app.utils.audit_helper import log_audit
logger = get_logger(__name__)
router = APIRouter(prefix="/employees", tags=["employees"])

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_employee(
    employee: EmployeeCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["employee.create"], check_tenant=True)),
):
    """
    Create a new employee.

    Rules:
    - Vendors/Drivers → forbidden
    - Employees → tenant_id enforced from token
    - Admins → must provide tenant_id in payload

    Returns:
    - EmployeeResponse wrapped in ResponseWrapper
    """
    try:
        user_type = user_data.get("user_type")
        tenant_id = None

        # 🚫 Vendors/Drivers cannot create employees
        if user_type in {"vendor", "driver"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to create employees",
                    error_code="FORBIDDEN",
                ),
            )

        # 🔒 Tenant enforcement
        if user_type == "employee":
            tenant_id = user_data.get("tenant_id")
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
        elif user_type == "admin":
            if not employee.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Tenant ID is required for admin",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
            tenant_id = employee.tenant_id
        logger.debug(f"Creating employee under tenant_id: {tenant_id}")
        tenant = tenant_crud.get_by_id(db=db, tenant_id=tenant_id)
        tenant_id = tenant.tenant_id if tenant else None
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message=f"Tenant with ID {tenant_id} does not exist",
                    error_code="INVALID_TENANT_ID",
                ),
            )
        if not team_crud.is_team_in_tenant(db, team_id=employee.team_id, tenant_id=tenant_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message=f"Team with ID {employee.team_id} does not belong to tenant {tenant_id}",
                    error_code="TEAM_TENANT_MISMATCH",
                ),
            )



        db_employee = employee_crud.create_with_tenant(db=db, obj_in=employee, tenant_id=tenant_id)
        logger.debug(f"Created employee object: {db_employee}")
        if not db_employee:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ResponseWrapper.error(
                    message="Failed to create employee",
                    error_code="EMPLOYEE_CREATION_FAILED",
                ),
            )
        # 🔥 Add background email task
        background_tasks.add_task(
            send_employee_created_email,
            employee_data={
                "name": db_employee.name,
                "email": db_employee.email,
                "phone": db_employee.phone,
                "employee_id": db_employee.employee_id,
                "tenant_id": tenant_id,
                "team_id": db_employee.team_id,
            },
        )
        db.commit()
        db.refresh(db_employee)

        # 🔍 Audit Log: Employee Creation
        try:
            employee_data_for_audit = {
                "employee_id": db_employee.employee_id,
                "name": db_employee.name,
                "email": db_employee.email,
                "phone": db_employee.phone,
                "employee_code": db_employee.employee_code,
                "team_id": db_employee.team_id,
                "is_active": db_employee.is_active
            }
            log_audit(
                db=db,
                tenant_id=tenant_id,
                module="employee",
                action="CREATE",
                user_data=user_data,
                description=f"Created employee '{db_employee.name}' ({db_employee.email})",
                new_values=employee_data_for_audit,
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for employee creation: {str(audit_error)}")

        logger.info(
            f"Employee created successfully under tenant {tenant_id}: "
            f"employee_id={db_employee.employee_id}, name={db_employee.name}"
        )

        employee_response = EmployeeResponse.model_validate(db_employee, from_attributes=True).model_dump()
        # Add tenant location details
        if db_employee.tenant:
            employee_response["tenant_latitude"] = float(db_employee.tenant.latitude) if db_employee.tenant.latitude else None
            employee_response["tenant_longitude"] = float(db_employee.tenant.longitude) if db_employee.tenant.longitude else None
            employee_response["tenant_address"] = db_employee.tenant.address

        return ResponseWrapper.success(
            data={"employee": employee_response},
            message="Employee created successfully",
        )   

    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while creating employee: {str(e)}")
        raise handle_http_error(e)

def send_employee_created_email(employee_data: dict):
    """Background task to send employee creation email."""
    try:
        email_service = get_email_service()

        success = email_service.send_employee_created_email(
            user_email=employee_data["email"],
            user_name=employee_data["name"],
            details=employee_data,
        )

        if success:
            logger.info(f"Employee creation email sent: {employee_data['employee_id']}")
        else:
            logger.error(f"Employee creation email FAILED: {employee_data['employee_id']}")

    except Exception as e:
        logger.error(f"Error sending employee creation email: {str(e)}")

@router.get("/", status_code=status.HTTP_200_OK)
def read_employees(
    skip: int = 0,
    limit: int = 100,
    name: Optional[str] = None,
    tenant_id: Optional[str] = None,
    team_id: Optional[int] = None,
    is_active: Optional[bool] = None,  # 👈 Added filter
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["employee.read"], check_tenant=True)),
):
    """
    Fetch employees with role-based restrictions:
    - driver/vendor → forbidden
    - employee → only within their tenant
    - admin → must filter by tenant_id
    - team_id → optional filter, must belong to the same tenant
    - is_active → optional filter
    """
    try:
        user_type = user_data.get("user_type")

        # 🚫 Vendors/Drivers forbidden
        if user_type in {"vendor", "driver"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to view employees",
                    error_code="FORBIDDEN",
                ),
            )

        # Tenant enforcement
        if user_type == "employee":
            tenant_id = user_data.get("tenant_id")
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )

        elif user_type == "admin":
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Tenant ID is required for admin",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )

            # Ensure tenant exists
            if not tenant_crud.get_by_id(db, tenant_id=tenant_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        message=f"Tenant {tenant_id} not found",
                        error_code="TENANT_NOT_FOUND",
                    ),
                )

        # --- Team filter check ---
        if team_id is not None:
            team = team_crud.get_by_id(db, team_id=team_id)
            if not team or team.tenant_id != tenant_id:  # 🔒 enforce tenant match
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message=f"Team {team_id} does not belong to tenant {tenant_id}",
                        error_code="TEAM_NOT_IN_TENANT",
                    ),
                )

        # Query employees
        query = db.query(Employee).filter(Employee.tenant_id == tenant_id)

        if name:
            query = query.filter(Employee.name.ilike(f"%{name}%"))
        if team_id is not None:
            query = query.filter(Employee.team_id == team_id)
        if is_active is not None:  # 👈 Apply is_active filter
            query = query.filter(Employee.is_active == is_active)

        total, items = paginate_query(query, skip, limit)

        employees = []
        for emp in items:
            emp_dict = EmployeeResponse.model_validate(emp, from_attributes=True).model_dump()
            # Add tenant location details
            if emp.tenant:
                emp_dict["tenant_latitude"] = float(emp.tenant.latitude) if emp.tenant.latitude else None
                emp_dict["tenant_longitude"] = float(emp.tenant.longitude) if emp.tenant.longitude else None
                emp_dict["tenant_address"] = emp.tenant.address
            employees.append(emp_dict)

        return ResponseWrapper.success(
            data={"total": total, "items": employees},
            message="Employees fetched successfully"
        )

    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while fetching employees: {str(e)}")
        raise handle_http_error(e)

@router.get("/{employee_id}", status_code=status.HTTP_200_OK)
def read_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["employee.read"], check_tenant=True)),
):
    """
    Fetch an employee by ID with role-based restrictions:
    - driver/vendor → forbidden
    - employee → only within their tenant
    - admin → unrestricted (but tenant_id should still match employee)
    """
    try:
        user_type = user_data.get("user_type")
        tenant_id = user_data.get("tenant_id")

        # 🚫 Vendors/Drivers forbidden
        if user_type in {"vendor", "driver"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to view employees",
                    error_code="FORBIDDEN",
                ),
            )

        # 🔒 Tenant enforcement
        query = db.query(Employee).filter(Employee.employee_id == employee_id)
        if user_type == "employee":
            query = query.filter(Employee.tenant_id == tenant_id)

        db_employee = query.first()
        if not db_employee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Employee with ID {employee_id} not found",
                    error_code="EMPLOYEE_NOT_FOUND",
                ),
            )

        employee_data = EmployeeResponse.model_validate(db_employee, from_attributes=True).model_dump()
        # Add tenant location details
        if db_employee.tenant:
            employee_data["tenant_latitude"] = float(db_employee.tenant.latitude) if db_employee.tenant.latitude else None
            employee_data["tenant_longitude"] = float(db_employee.tenant.longitude) if db_employee.tenant.longitude else None
            employee_data["tenant_address"] = db_employee.tenant.address

        return ResponseWrapper.success(
            data={"employee": employee_data}, message="Employee fetched successfully"
        )

    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while fetching employee {employee_id}: {str(e)}")
        raise handle_http_error(e)

@router.put("/{employee_id}", status_code=status.HTTP_200_OK)
def update_employee(
    employee_id: int,
    employee_update: EmployeeUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["employee.update"], check_tenant=True)),
):
    """
    Update an employee with role-based restrictions:
    - driver/vendor → forbidden
    - employee → only within their tenant
    - admin → must provide valid tenant_id (employee must belong to that tenant)
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # 🚫 Vendors/Drivers forbidden
        if user_type in {"vendor", "driver"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to update employees",
                    error_code="FORBIDDEN",
                ),
            )

        # Fetch employee
        db_employee = db.query(Employee).filter(Employee.employee_id == employee_id).first()
        if not db_employee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Employee with ID {employee_id} not found",
                    error_code="EMPLOYEE_NOT_FOUND",
                ),
            )

        # 🔍 Capture old values before update
        old_values = {}
        update_data = employee_update.model_dump(exclude_unset=True)
        for key in update_data.keys():
            if key != "password":  # Don't log password
                old_val = getattr(db_employee, key, None)
                if old_val is not None:
                    old_values[key] = str(old_val) if not isinstance(old_val, (str, int, float, bool)) else old_val

        # 🔒 Tenant enforcement
        if user_type == "employee":
            if db_employee.tenant_id != token_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="You cannot update employees outside your tenant",
                        error_code="TENANT_FORBIDDEN",
                    ),
                )
        elif user_type == "admin":
            if not db_employee.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Employee tenant is missing in DB",
                        error_code="TENANT_MISSING",
                    ),
                )
            tenant = tenant_crud.get_by_id(db, tenant_id=db_employee.tenant_id)
            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        message=f"Tenant {db_employee.tenant_id} not found",
                        error_code="TENANT_NOT_FOUND",
                    ),
                )

        # Apply updates (already captured above)
        if "password" in update_data:
            update_data["password"] = hash_password(update_data["password"])

        # 🚦 Team validation if updating team_id
        if "team_id" in update_data and update_data["team_id"] is not None:
            if not team_crud.is_team_in_tenant(
                db, team_id=update_data["team_id"], tenant_id=db_employee.tenant_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message=f"Team {update_data['team_id']} does not belong to tenant {db_employee.tenant_id}",
                        error_code="TEAM_TENANT_MISMATCH",
                    ),
                )

        # 🔐 Role validation if updating role_id
        if "role_id" in update_data and update_data["role_id"] is not None:
            from app.crud.iam.role import role_crud
            role = role_crud.get(db, id=update_data["role_id"])
            if not role:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        message=f"Role with ID {update_data['role_id']} not found",
                        error_code="ROLE_NOT_FOUND",
                    ),
                )
            # Validate role belongs to the same tenant (or is a system role)
            if role.tenant_id and role.tenant_id != db_employee.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message=f"Role {update_data['role_id']} does not belong to tenant {db_employee.tenant_id}",
                        error_code="ROLE_TENANT_MISMATCH",
                    ),
                )

        for key, value in update_data.items():
            setattr(db_employee, key, value)

        db.commit()
        db.refresh(db_employee)

        # 🔍 Capture new values after update
        new_values = {}
        for key in update_data.keys():
            if key != "password":  # Don't log password
                new_val = getattr(db_employee, key, None)
                if new_val is not None:
                    new_values[key] = str(new_val) if not isinstance(new_val, (str, int, float, bool)) else new_val

        # 🔍 Audit Log: Employee Update
        try:
            # Build description with changed fields
            changed_fields = list(update_data.keys())
            fields_str = ", ".join(changed_fields) if changed_fields else "details"
            
            log_audit(
                db=db,
                tenant_id=db_employee.tenant_id,
                module="employee",
                action="UPDATE",
                user_data=user_data,
                description=f"Updated employee '{db_employee.name}' - changed fields: {fields_str}",
                new_values={"old": old_values, "new": new_values},
                request=request
            )
            logger.info(f"Audit log created for employee update")
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for employee update: {str(audit_error)}", exc_info=True)

        logger.info(
            f"Employee updated successfully: employee_id={employee_id}, tenant_id={db_employee.tenant_id}"
        )

        employee_response = EmployeeResponse.model_validate(db_employee, from_attributes=True).model_dump()
        # Add tenant location details
        if db_employee.tenant:
            employee_response["tenant_latitude"] = float(db_employee.tenant.latitude) if db_employee.tenant.latitude else None
            employee_response["tenant_longitude"] = float(db_employee.tenant.longitude) if db_employee.tenant.longitude else None
            employee_response["tenant_address"] = db_employee.tenant.address

        return ResponseWrapper.success(
            data={"employee": employee_response},
            message="Employee updated successfully",
        )

    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while updating employee {employee_id}: {str(e)}")
        raise handle_http_error(e)

@router.patch("/{employee_id}/toggle-status", status_code=status.HTTP_200_OK)
def toggle_employee_status(
    employee_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["employee.update"], check_tenant=True)),
):
    """
    Toggle employee active/inactive status.
    - driver/vendor → forbidden
    - employee → only within their tenant
    - admin → must belong to tenant
    """
    try:
        user_type = user_data.get("user_type")
        token_tenant_id = user_data.get("tenant_id")

        # 🚫 Vendors/Drivers forbidden
        if user_type in {"vendor", "driver"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to modify employees",
                    error_code="FORBIDDEN",
                ),
            )

        # Fetch employee
        db_employee = db.query(Employee).filter(Employee.employee_id == employee_id).first()
        if not db_employee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Employee with ID {employee_id} not found",
                    error_code="EMPLOYEE_NOT_FOUND",
                ),
            )

        # 🔍 Capture old status for audit
        old_status = db_employee.is_active

        # 🔒 Tenant enforcement
        if user_type == "employee":
            if db_employee.tenant_id != token_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="You cannot modify employees outside your tenant",
                        error_code="TENANT_FORBIDDEN",
                    ),
                )
        elif user_type == "admin":
            tenant = tenant_crud.get_by_id(db, tenant_id=db_employee.tenant_id)
            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        message=f"Tenant {db_employee.tenant_id} not found",
                        error_code="TENANT_NOT_FOUND",
                    ),
                )

        # 🚦 Toggle status
        old_status = db_employee.is_active
        db_employee.is_active = not db_employee.is_active
        db.commit()
        db.refresh(db_employee)

        # 🔍 Audit Log: Status Toggle
        try:
            status_text = 'active' if db_employee.is_active else 'inactive'
            log_audit(
                db=db,
                tenant_id=db_employee.tenant_id,
                module="employee",
                action="UPDATE",
                user_data=user_data,
                description=f"Toggled employee '{db_employee.name}' status to {status_text}",
                new_values={"old_status": old_status, "new_status": db_employee.is_active},
                request=request
            )
        except Exception as audit_error:
            logger.error(f"Failed to create audit log for status toggle: {str(audit_error)}")

        logger.info(
            f"Employee {employee_id} status toggled to "
            f"{'active' if db_employee.is_active else 'inactive'} "
            f"(tenant_id={db_employee.tenant_id})"
        )

        return ResponseWrapper.success(
            data={
                "employee_id": db_employee.employee_id,
                "is_active": db_employee.is_active,
            },
            message=f"Employee status updated to {'active' if db_employee.is_active else 'inactive'}",
        )

    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while toggling employee {employee_id} status: {str(e)}")
        raise handle_http_error(e)

# @router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
# def delete_employee(
#     employee_id: int, 
#     db: Session = Depends(get_db),
#     user_data=Depends(PermissionChecker(["employee.delete"], check_tenant=True))
# ):
#     db_employee = db.query(Employee).filter(Employee.employee_id == employee_id).first()
#     if not db_employee:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Employee with ID {employee_id} not found"
#         )
    
#     db.delete(db_employee)
#     db.commit()
#     return None

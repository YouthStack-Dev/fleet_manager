from fastapi import APIRouter, Depends, HTTPException, status, Query
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
logger = get_logger(__name__)
router = APIRouter(prefix="/employees", tags=["employees"])

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_employee(
    employee: EmployeeCreate,
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
        db.commit()
        db.refresh(db_employee)

        logger.info(
            f"Employee created successfully under tenant {tenant_id}: "
            f"employee_id={db_employee.employee_id}, name={db_employee.name}"
        )

        return ResponseWrapper.success(
            data={"employee": EmployeeResponse.model_validate(db_employee, from_attributes=True)},
            message="Employee created successfully",
        )   

    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while creating employee: {str(e)}")
        raise handle_http_error(e)


@router.get("/", response_model=EmployeePaginationResponse)
def read_employees(
    skip: int = 0,
    limit: int = 100,
    name: Optional[str] = None,
    email: Optional[str] = None,
    team_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["employee.read"], check_tenant=True))
):
    query = db.query(Employee)
    
    # Apply filters
    if name:
        query = query.filter(Employee.name.ilike(f"%{name}%"))
    if email:
        query = query.filter(Employee.email.ilike(f"%{email}%"))
    if team_id:
        query = query.filter(Employee.team_id == team_id)
    if is_active is not None:
        query = query.filter(Employee.is_active == is_active)
    
    total, items = paginate_query(query, skip, limit)
    return {"total": total, "items": items}

@router.get("/{employee_id}", response_model=EmployeeResponse)
def read_employee(
    employee_id: int, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["employee.read"], check_tenant=True))
):
    db_employee = db.query(Employee).filter(Employee.employee_id == employee_id).first()
    if not db_employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee with ID {employee_id} not found"
        )
    return db_employee

@router.put("/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: int, 
    employee_update: EmployeeUpdate, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["employee.update"], check_tenant=True))
):
    db_employee = db.query(Employee).filter(Employee.employee_id == employee_id).first()
    if not db_employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee with ID {employee_id} not found"
        )
    
    update_data = employee_update.dict(exclude_unset=True)
    
    # Hash password if it's being updated
    if "password" in update_data:
        update_data["password"] = hash_password(update_data["password"])
    
    for key, value in update_data.items():
        setattr(db_employee, key, value)
    
    db.commit()
    db.refresh(db_employee)
    return db_employee

@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(
    employee_id: int, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["employee.delete"], check_tenant=True))
):
    db_employee = db.query(Employee).filter(Employee.employee_id == employee_id).first()
    if not db_employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee with ID {employee_id} not found"
        )
    
    db.delete(db_employee)
    db.commit()
    return None

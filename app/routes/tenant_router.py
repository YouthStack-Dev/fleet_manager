from sqlite3 import IntegrityError
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.models.iam.permission import Permission
from app.models.iam.policy import Policy
from app.models.iam.role import Role
from app.models.tenant import Tenant
from app.crud.tenant import tenant_crud
from app.crud.team import team_crud
from app.crud.employee import employee_crud
from app.schemas.employee import EmployeeCreate, EmployeeResponse
from app.schemas.iam.policy import PolicyResponse
from app.schemas.iam.role import RoleResponse
from app.schemas.team import TeamCreate, TeamResponse
from app.schemas.tenant import TenantCreate, TenantUpdate, TenantResponse, TenantPaginationResponse
from app.utils.pagination import paginate_query
from app.utils.response_utils import ResponseWrapper
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger
logger = get_logger(__name__)
router = APIRouter(prefix="/tenants", tags=["tenants"])




@router.post("/", status_code=status.HTTP_201_CREATED)
def create_tenant(
    tenant: TenantCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["admin.tenant.create"], check_tenant=False)),
    default_team_name: str = "Default Team",
    default_team_desc: str = "Auto-created team for this tenant"
):
    logger.info(f"Create tenant request received: {tenant.dict()}")

    try:
        with db.begin():  # Ensures atomic commit/rollback
            # --- Check duplicates ---
            if tenant_crud.get_by_id(db, tenant_id=tenant.tenant_id):
                logger.warning(f"Tenant creation failed - duplicate id: {tenant.tenant_id}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=ResponseWrapper.error(
                        message=f"Tenant with id '{tenant.tenant_id}' already exists",
                        error_code=status.HTTP_409_CONFLICT
                    )
                )

            if tenant_crud.get_by_name(db, name=tenant.name):
                logger.warning(f"Tenant creation failed - duplicate name: {tenant.name}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=ResponseWrapper.error(
                        message=f"Tenant with name '{tenant.name}' already exists",
                        error_code=status.HTTP_409_CONFLICT
                    )
                )

            # --- Create tenant ---
            new_tenant = tenant_crud.create(db, obj_in=tenant)
            logger.info(f"Tenant created successfully: {new_tenant.tenant_id}")

            # --- Create default team ---
            default_team = team_crud.create(
                db,
                obj_in=TeamCreate(
                    tenant_id=new_tenant.tenant_id,
                    name=f"{default_team_name}_{new_tenant.tenant_id}",
                    description=default_team_desc
                )
            )
            logger.info(f"Default team created: {default_team.name}")

            # --- Create Admin Role ---
            admin_role_name = f"{new_tenant.tenant_id}_Admin"
            admin_role = Role(
                tenant_id=new_tenant.tenant_id,
                name=admin_role_name,
                description=f"Admin role for tenant {new_tenant.name}",
                is_active=True,
            )
            db.add(admin_role)
            db.flush()
            logger.info(f"Admin role created: {admin_role_name}")

            # --- Create Admin Policy ---
            admin_policy_name = f"{new_tenant.tenant_id}_AdminPolicy"
            admin_policy = Policy(
                name=admin_policy_name,
                description=f"Admin policy for tenant {new_tenant.name}",
                is_active=True
            )
            db.add(admin_policy)
            db.flush()
            logger.info(f"Tenant policy created: {admin_policy_name}")

            # --- Attach permissions ---
            if tenant.permission_ids:
                permissions = (
                    db.query(Permission)
                    .filter(Permission.permission_id.in_(tenant.permission_ids))
                    .all()
                )

                found_ids = {p.permission_id for p in permissions}
                missing_ids = set(tenant.permission_ids) - found_ids
                if missing_ids:
                    logger.warning(
                        f"Invalid permission IDs {list(missing_ids)} for tenant {new_tenant.tenant_id}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ResponseWrapper.error(
                            message="Some permission IDs are invalid",
                            error_code=status.HTTP_400_BAD_REQUEST,
                            details={"invalid_permission_ids": list(missing_ids)},
                        ),
                    )

                admin_policy.permissions = permissions
                logger.info(
                    f"Attached permissions {[p.permission_id for p in permissions]} "
                    f"({[p.module + ':' + p.action for p in permissions]}) "
                    f"to policy {admin_policy_name}"
                )

            # --- Link Role to Policy ---
            admin_role.policies.append(admin_policy)
            logger.info(f"Linked role {admin_role_name} to policy {admin_policy_name}")

            # --- Create Employee (Tenant Admin User) ---
            employee_name = tenant.employee_name or f"Admin_{new_tenant.tenant_id}"
            employee_email = tenant.employee_email
            employee_phone = tenant.employee_phone

            if not employee_email or not employee_phone:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Employee email and phone are mandatory",
                        error_code=status.HTTP_400_BAD_REQUEST,
                    ),
                )

            employee_in = EmployeeCreate(
                tenant_id=new_tenant.tenant_id,
                role_id=admin_role.role_id,
                team_id=default_team.team_id,
                name=employee_name,
                employee_code=tenant.employee_code or f"EMP_{new_tenant.tenant_id}_001",
                email=employee_email,
                password=tenant.employee_password or "default@123",
                phone=employee_phone,
                address=tenant.employee_address,
                longitude=tenant.employee_longitude,
                latitude=tenant.employee_latitude,
                gender=tenant.employee_gender,
                is_active=True,
            )

            new_employee = employee_crud.create_with_tenant(
                db, obj_in=employee_in, tenant_id=new_tenant.tenant_id
            )
            logger.info(
                f"Employee created for tenant {new_tenant.tenant_id}: "
                f"{new_employee.name} ({new_employee.email})"
            )

        # --- Response ---
        return ResponseWrapper.success(
            data={
                "tenant": TenantResponse.model_validate(new_tenant),
                "team": TeamResponse.model_validate(default_team),
                "admin_role": RoleResponse.model_validate(admin_role),
                "admin_policy": PolicyResponse.model_validate(admin_policy),
                "employee": EmployeeResponse.model_validate(new_employee),
            },
            message="Tenant, default team, admin role, policy, and employee created successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while creating tenant: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Unexpected server error while creating tenant",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"error": str(e)}
            )
        )

@router.get("/", response_model=TenantPaginationResponse)
def read_tenants(
    skip: int = 0,
    limit: int = 100,
    name: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["admin.tenant.read"], check_tenant=False))
):
    query = db.query(Tenant)
    
    # Apply filters
    if name:
        query = query.filter(Tenant.name.ilike(f"%{name}%"))
    if is_active is not None:
        query = query.filter(Tenant.is_active == is_active)
    
    total, items = paginate_query(query, skip, limit)
    return {"total": total, "items": items}

@router.get("/{tenant_id}", response_model=TenantResponse)
def read_tenant(
    tenant_id: str, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["admin.tenant.read"], check_tenant=False))
):
    db_tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with ID {tenant_id} not found"
        )
    return db_tenant

@router.put("/{tenant_id}", response_model=TenantResponse)
def update_tenant(
    tenant_id: str, 
    tenant_update: TenantUpdate, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["admin.tenant.update"], check_tenant=False))
):
    db_tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with ID {tenant_id} not found"
        )
    
    update_data = tenant_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_tenant, key, value)
    
    db.commit()
    db.refresh(db_tenant)
    return db_tenant

@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tenant(
    tenant_id: str, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["admin.tenant.delete"], check_tenant=False))
):
    db_tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not db_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with ID {tenant_id} not found"
        )
    
    db.delete(db_tenant)
    db.commit()
    return None

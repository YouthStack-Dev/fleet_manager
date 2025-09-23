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
from app.utils.response_utils import ResponseWrapper , handle_db_error
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger
logger = get_logger(__name__)
router = APIRouter(prefix="/tenants", tags=["tenants"])




@router.post("/", status_code=status.HTTP_201_CREATED)
def create_tenant(
    tenant: TenantCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["admin.tenant.create"], check_tenant=False)),
    
):
    """
    Create a new tenant with associated default team, admin role, policy, and employee.

    **Required permissions:** `admin.tenant.create`

    **Request body:**

    * `tenant_id`: Unique identifier for the tenant.
    * `name`: Name of the tenant.
    * `employee_name`: Name of the employee (tenant admin user).
    * `employee_email`: Email of the employee (tenant admin user).
    * `employee_phone`: Phone number of the employee (tenant admin user).
    * `employee_password`: Password of the employee (tenant admin user) (optional).
    * `employee_address`: Address of the employee (tenant admin user) (optional).
    * `employee_longitude`: Longitude of the employee (tenant admin user) (optional).
    * `employee_latitude`: Latitude of the employee (tenant admin user) (optional).
    * `employee_gender`: Gender of the employee (tenant admin user) (optional).
    * `employee_code`: Code of the employee (tenant admin user) (optional).
    * `permission_ids`: List of permission IDs to attach to the admin role (optional).

    **Response:**

    * `tenant`: Newly created tenant object.
    * `team`: Newly created default team object.
    * `admin_role`: Newly created admin role object.
    * `admin_policy`: Newly created admin policy object.
    * `employee`: Newly created employee object.

    **Status codes:**

    * `201 Created`: Tenant created successfully.
    * `400 Bad Request`: Invalid request body or permission IDs.
    * `409 Conflict`: Tenant with the same ID or name already exists.
    * `500 Internal Server Error`: Unexpected server error while creating tenant.
    """
    logger.info(f"Create tenant request received: {tenant.dict()}")

    try:
        # --- Restrict access ---
        if user_data.get("user_type") not in ["admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Please contact admin for creation",
                    error_code="FORBIDDEN",
                ),
            )

        with db.begin():  # Ensures atomic commit/rollback
            # --- Check duplicates ---
            if tenant_crud.get_by_id(db, tenant_id=tenant.tenant_id):
                logger.warning(f"Tenant creation failed - duplicate id: {tenant.tenant_id}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=ResponseWrapper.error(
                        message=f"Tenant with id '{tenant.tenant_id}' already exists",
                        error_code=status.HTTP_409_CONFLICT,
                    ),
                )

            if tenant_crud.get_by_name(db, name=tenant.name):
                logger.warning(f"Tenant creation failed - duplicate name: {tenant.name}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=ResponseWrapper.error(
                        message=f"Tenant with name '{tenant.name}' already exists",
                        error_code=status.HTTP_409_CONFLICT,
                    ),
                )

            default_team_name: str = "Default Team"
            default_team_desc: str = "Auto-created team for this tenant"
            # --- Create tenant ---
            new_tenant = tenant_crud.create(db, obj_in=tenant)
            logger.info(f"Tenant created successfully: {new_tenant.tenant_id}")

            # --- Create default team ---
            default_team = team_crud.create(
                db,
                obj_in=TeamCreate(
                    tenant_id=new_tenant.tenant_id,
                    name=f"{default_team_name}_{new_tenant.tenant_id}",
                    description=default_team_desc,
                ),
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
                tenant_id=new_tenant.tenant_id,
                name=admin_policy_name,
                description=f"Admin policy for tenant {new_tenant.name}",
                is_active=True,
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
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=ResponseWrapper.error(
                            message="Some permission IDs are not found or invalid",
                            error_code=status.HTTP_404_NOT_FOUND,
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
            message="Tenant, default team, admin role, policy, and employee created successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while creating tenant: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Unexpected server error while creating tenant",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"error": str(e)},
            ),
        )
@router.get("/", response_model=dict, status_code=status.HTTP_200_OK)
def read_tenants(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Max number of records to fetch"),
    name: Optional[str] = Query(None, description="Filter tenants by name (case-insensitive)"),
    is_active: Optional[bool] = Query(None, description="Filter tenants by active status"),
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["admin.tenant.read"], check_tenant=False)),
):

    """
    Fetch a list of tenants with optional filters.

    Rules:
    - user_type == vendor/driver or missing → Forbidden
    - user_type == employee → can fetch only their tenant
    - other (admin/superadmin) → can apply filters and fetch multiple tenants
    """
    try:
        # 🚫 Block unauthorized user types
        if not user_data or user_data.get("user_type") in {"vendor", "driver"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to access this resource",
                    error_code="FORBIDDEN",
                ),
            )

        query = db.query(Tenant)

        # 👷 Employee restriction
        if user_data.get("user_type") == "employee":
            tenant_id = user_data.get("tenant_id")
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
            query = query.filter(Tenant.tenant_id == tenant_id)

        # 👑 Admin/SuperAdmin filters
        else:
            if name:
                query = query.filter(Tenant.name.ilike(f"%{name}%"))
            if is_active is not None:
                query = query.filter(Tenant.is_active == is_active)

        total, items = paginate_query(query, skip, limit)
        tenants = [TenantResponse.model_validate(t, from_attributes=True) for t in items]

        logger.info(
            f"Fetched {len(tenants)} tenants (total={total}, skip={skip}, limit={limit}) "
            f"for user {user_data.get('user_id')} of type {user_data.get('user_type')}"
        )

        return ResponseWrapper.success(
            data=TenantPaginationResponse(total=total, items=tenants),
            message="Tenants fetched successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise handle_db_error(e)
    except Exception as e:
        logger.exception(f"Unexpected error while fetching tenants: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Unexpected error while fetching tenants",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"error": str(e)},
            ),
        )


@router.get("/{tenant_id}", response_model=dict, status_code=status.HTTP_200_OK)
def read_tenant(
    tenant_id: str,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["admin.tenant.read"], check_tenant=False)),
):
    """
    Fetch a tenant by ID.

    Rules:
    - vendors/drivers → forbidden
    - employees → always restricted to their own tenant_id from token (ignores path param)
    - admins/superadmins → can fetch by provided tenant_id
    """
    try:
        # 🚫 Block unauthorized user types
        if not user_data or user_data.get("user_type") in {"vendor", "driver"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to access this resource",
                    error_code="FORBIDDEN",
                ),
            )

        # 👷 Employee restriction
        if user_data.get("user_type") == "employee":
            token_tenant_id = user_data.get("tenant_id")
            if not token_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
            # 🚨 Force override → ignore the requested tenant_id
            tenant_id = token_tenant_id

        # 👑 Admin/SuperAdmin → tenant_id is taken directly from path param

        db_tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()

        if not db_tenant:
            logger.warning(f"Tenant fetch failed - not found: {tenant_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Tenant with ID '{tenant_id}' not found",
                    error_code=status.HTTP_404_NOT_FOUND,
                ),
            )

        tenant = TenantResponse.model_validate(db_tenant, from_attributes=True)

        logger.info(f"Tenant fetched successfully: {tenant_id}")

        return ResponseWrapper.success(
            data=tenant,
            message="Tenant fetched successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while fetching tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message=f"Unexpected error while fetching tenant '{tenant_id}'",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"error": str(e)},
            ),
        )
@router.put("/{tenant_id}", response_model=dict, status_code=status.HTTP_200_OK)
def update_tenant(
    tenant_id: str,
    tenant_update: TenantUpdate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["admin.tenant.update"], check_tenant=False)),
):
    """
    Update a tenant by ID.

    Rules:
    - Only admins/superadmins can update.
    - Employees, vendors, and drivers → blocked with a clear message.
    """
    try:
        # 🚫 Block employees, vendors, drivers explicitly
        if not user_data or user_data.get("user_type") in {"employee", "vendor", "driver"}:
            logger.warning(
                f"Unauthorized tenant update attempt by user {user_data.get('user_id')} "
                f"of type {user_data.get('user_type')} on tenant {tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don’t have permission to update tenant details. "
                            "Please contact your superadmin for changes.",
                    error_code="FORBIDDEN",
                ),
            )

        # ✅ Admin/SuperAdmin logic
        db_tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        if not db_tenant:
            logger.warning(f"Tenant update failed - not found: {tenant_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Tenant with ID '{tenant_id}' not found",
                    error_code=status.HTTP_404_NOT_FOUND,
                ),
            )

        update_data = tenant_update.dict(exclude_unset=True)
        if not update_data:
            logger.warning(f"No update fields provided for tenant: {tenant_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ResponseWrapper.error(
                    message="No valid fields provided for update",
                    error_code=status.HTTP_400_BAD_REQUEST,
                ),
            )

        for key, value in update_data.items():
            setattr(db_tenant, key, value)

        db.commit()
        db.refresh(db_tenant)

        updated_tenant = TenantResponse.model_validate(db_tenant, from_attributes=True)
        logger.info(f"Tenant updated successfully: {tenant_id}")

        return ResponseWrapper.success(
            data=updated_tenant,
            message=f"Tenant '{tenant_id}' updated successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while updating tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message=f"Unexpected error while updating tenant '{tenant_id}'",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"error": str(e)},
            ),
        )

@router.patch("/{tenant_id}/toggle-status", response_model=dict, status_code=status.HTTP_200_OK)
def toggle_tenant_status(
    tenant_id: str,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["admin.tenant.update"], check_tenant=False)),
):
    """
    Toggle a tenant's active status (Admins only).
    """
    try:
        # --- Restrict access ---
        if user_data.get("user_type") not in ["admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="Please contact your admin for changes",
                    error_code="FORBIDDEN",
                ),
            )

        db_tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
        if not db_tenant:
            logger.warning(f"Tenant toggle failed - not found: {tenant_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ResponseWrapper.error(
                    message=f"Tenant with ID '{tenant_id}' not found",
                    error_code=status.HTTP_404_NOT_FOUND,
                ),
            )

        # --- Toggle status ---
        db_tenant.is_active = not db_tenant.is_active
        db.commit()
        db.refresh(db_tenant)

        logger.info(
            f"Toggled tenant {tenant_id} status to {'active' if db_tenant.is_active else 'inactive'}"
        )

        return ResponseWrapper.success(
            data=TenantResponse.model_validate(db_tenant, from_attributes=True),
            message=f"Tenant '{tenant_id}' is now {'active' if db_tenant.is_active else 'inactive'}",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise handle_db_error(e)
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while toggling tenant {tenant_id} status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message=f"Unexpected error while toggling tenant '{tenant_id}' status",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"error": str(e)},
            ),
        )


# @router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
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

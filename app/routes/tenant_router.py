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

    Args:
        skip (int): Number of records to skip.
        limit (int): Max number of records to fetch.
        name (Optional[str]): Filter tenants by name (case-insensitive).
        is_active (Optional[bool]): Filter tenants by active status.

    Returns:
        ResponseWrapper: a successful response with the fetched tenant data.
    """
    try:
        query = db.query(Tenant)

        # --- Apply filters ---
        if name:
            query = query.filter(Tenant.name.ilike(f"%{name}%"))
        if is_active is not None:
            query = query.filter(Tenant.is_active == is_active)

        total, items = paginate_query(query, skip, limit)

        tenants = [TenantResponse.model_validate(t, from_attributes=True) for t in items]

        logger.info(f"Fetched {len(tenants)} tenants (total={total}, skip={skip}, limit={limit})")

        return ResponseWrapper.success(
            data=TenantPaginationResponse(total=total, items=tenants),
            message="Tenants fetched successfully"
        )

    except Exception as e:
        logger.exception(f"Unexpected error while fetching tenants: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Unexpected error while fetching tenants",
                error_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                details={"error": str(e)}
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

    **Required permissions:** `admin.tenant.read`

    **Response:**

    * `tenant`: Tenant object with the given ID.

    **Status codes:**

    * `200 OK`: Tenant fetched successfully.
    * `404 Not Found`: Tenant with the given ID not found.
    * `500 Internal Server Error`: Unexpected server error while fetching tenant.
    """
    try:
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
            message="Tenant fetched successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
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

    **Required permissions:** `admin.tenant.update`

    **Request body:**

    * `name`: Name of the tenant.
    * `is_active`: Active status of the tenant.

    **Response:**

    * `tenant`: Updated tenant object.

    **Status codes:**

    * `200 OK`: Tenant updated successfully.
    * `404 Not Found`: Tenant with the given ID not found.
    * `400 Bad Request`: No valid fields provided for update.
    * `500 Internal Server Error`: Unexpected server error while updating tenant.
    """
    try:
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
            message=f"Tenant '{tenant_id}' updated successfully"
        )

    except HTTPException:
        raise
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
    Toggle a tenant's active status.

    Requires "admin.tenant.update" permission.

    If tenant is not found, raises 404.

    If any other error occurs while toggling the tenant's status, raises 500.

    Args:
        tenant_id (str): The ID of the tenant to toggle.

    Returns:
        ResponseWrapper: A successful response with the updated tenant data.
    """
    try:
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
            message=f"Tenant '{tenant_id}' is now {'active' if db_tenant.is_active else 'inactive'}"
        )

    except HTTPException:
        raise
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

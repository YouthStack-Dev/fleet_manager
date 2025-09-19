from sqlite3 import IntegrityError
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.models.tenant import Tenant
from app.crud.tenant import tenant_crud
from app.crud.team import team_crud
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

        # --- Create default team for this tenant ---
        default_team = team_crud.create(
            db,
            obj_in=TeamCreate(
                tenant_id=new_tenant.tenant_id,
                name=default_team_name,
                description=default_team_desc
            )
        )
        logger.info(f"Default team created for tenant {new_tenant.tenant_id}: {default_team.name}")

        # --- Response ---
        return ResponseWrapper.success(
            data={
                "tenant": TenantResponse.model_validate(new_tenant),
                "team": TeamResponse.model_validate(default_team),
            },
            message="Tenant and default team created successfully"
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
    tenant_id: int, 
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
    tenant_id: int, 
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
    tenant_id: int, 
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

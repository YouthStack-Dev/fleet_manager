from email.mime import message
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.crud.tenant import tenant_crud
from app.database.session import get_db
from app.models.employee import Employee
from app.models.team import Team
from app.crud.team import team_crud
from sqlalchemy.exc import SQLAlchemyError
from app.models.tenant import Tenant
from app.schemas.team import TeamCreate, TeamUpdate, TeamResponse, TeamPaginationResponse
from app.utils.pagination import paginate_query
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_db_error, handle_http_error, handle_http_error
from common_utils.auth.permission_checker import PermissionChecker
from app.core.logging_config import get_logger
logger = get_logger(__name__)
router = APIRouter(prefix="/teams", tags=["teams"])

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_team(
    team: TeamCreate,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["team.create"], check_tenant=True)),
):
    """
    Create a new team.

    Rules:
    - 🚫 Vendors/Drivers → forbidden
    - 👷 Employees → tenant_id always taken from token (payload ignored)
    - 👑 Admin/SuperAdmin → must provide tenant_id in payload
    """
    try:
        user_type = user_data.get("user_type")

        # 🚫 Vendors/Drivers are not allowed
        if user_type in {"vendor", "driver"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to create teams",
                    error_code="FORBIDDEN",
                ),
            )

        tenant_id = None

        if user_type == "employee":
            # Employee → tenant_id forced from token
            tenant_id = user_data.get("tenant_id")
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )

        elif user_type in {"admin", "superadmin"}:
            # Admin/SuperAdmin → tenant_id must come from payload
            if not team.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Tenant ID is required for admin/superadmin",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )
            tenant_id = team.tenant_id

        # 🔄 Always override TeamCreate.tenant_id with the resolved one
        obj_in = TeamCreate(
            tenant_id=tenant_id,
            name=team.name,
            description=team.description,
        )

        db_team = team_crud.create(db, obj_in=obj_in)
        db.commit()
        db.refresh(db_team)

        logger.info(f"Team created successfully under tenant {tenant_id}: {db_team.name}")

        return ResponseWrapper.success(
            data={"team": TeamResponse.model_validate(db_team, from_attributes=True)},
            message="Team created successfully"
        )
    
    except SQLAlchemyError as e:
        # Handle DB errors in a structured way
        raise handle_db_error(e)
    except HTTPException:
        # Propagate known HTTPExceptions
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        logger.exception(f"Unexpected error while fetching vendors: {str(e)}")
        raise handle_http_error(e)

@router.get("/", status_code=status.HTTP_200_OK)
def read_teams(
    skip: int = 0,
    limit: int = 100,
    name: Optional[str] = None,
    tenant_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["team.read"], check_tenant=True)),
):
    """
    Fetch teams with pagination and employee counts.

    Rules:
    - 🚫 Vendors/Drivers → forbidden
    - 👷 Employees → tenant_id always taken from token
    - 👑 Admin/SuperAdmin → must provide tenant_id in query params (payload)
    """
    try:
        user_type = user_data.get("user_type")

        # 🚫 Vendors/Drivers are not allowed
        if user_type in {"vendor", "driver"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message="You don't have permission to view teams",
                    error_code="FORBIDDEN",
                ),
            )

        # --- Tenant validation ---
        if user_type == "employee":
            # Tenant comes strictly from token
            tenant_id = user_data.get("tenant_id")
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="Tenant ID missing in token for employee",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )

        elif user_type in {"admin"}:
            # Must come from query param
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message="Tenant ID is required for admin",
                        error_code="TENANT_ID_REQUIRED",
                    ),
                )

            # Check tenant exists
            tenant_exists = tenant_crud.get_by_id(db, tenant_id=tenant_id) is not None
            if not tenant_exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ResponseWrapper.error(
                        message=f"Tenant with ID {tenant_id} not found",
                        error_code="TENANT_NOT_FOUND",
                    ),
                )

        # --- Teams fetch ---
        query = db.query(Team).filter(Team.tenant_id == tenant_id)
        if name:
            query = query.filter(Team.name.ilike(f"%{name}%"))

        total, items = paginate_query(query, skip, limit)

        enriched_items = []
        for team in items:
            active_count = db.query(Employee).filter(
                Employee.team_id == team.team_id,
                Employee.is_active == True
            ).count()

            inactive_count = db.query(Employee).filter(
                Employee.team_id == team.team_id,
                Employee.is_active == False
            ).count()

            team_data = TeamResponse.model_validate(team, from_attributes=True).dict()
            team_data.update({
                "active_employee_count": active_count,
                "inactive_employee_count": inactive_count,
            })
            enriched_items.append(team_data)

        return ResponseWrapper.success(
            data={
                "total": total,
                "items": enriched_items,
            },
            message="Teams fetched successfully"
        )

    except SQLAlchemyError as e:
        raise handle_db_error(e)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while fetching teams: {str(e)}")
        raise handle_http_error(e)


@router.get("/{team_id}", response_model=TeamResponse)
def read_team(
    team_id: int, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["team.read"], check_tenant=True))
):
    db_team = db.query(Team).filter(Team.team_id == team_id).first()
    if not db_team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team with ID {team_id} not found"
        )
    return db_team

@router.put("/{team_id}", response_model=TeamResponse)
def update_team(
    team_id: int, 
    team_update: TeamUpdate, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["team.update"], check_tenant=True))
):
    db_team = db.query(Team).filter(Team.team_id == team_id).first()
    if not db_team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team with ID {team_id} not found"
        )
    
    update_data = team_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_team, key, value)
    
    db.commit()
    db.refresh(db_team)
    return db_team

@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(
    team_id: int, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["team.delete"], check_tenant=True))
):
    db_team = db.query(Team).filter(Team.team_id == team_id).first()
    if not db_team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team with ID {team_id} not found"
        )
    
    db.delete(db_team)
    db.commit()
    return None

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.models.team import Team
from app.schemas.team import TeamCreate, TeamUpdate, TeamResponse, TeamPaginationResponse
from app.utils.pagination import paginate_query
from common_utils.auth.permission_checker import PermissionChecker

router = APIRouter(prefix="/teams", tags=["teams"])

@router.post("/", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
def create_team(
    team: TeamCreate, 
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["team.create"], check_tenant=True))
):
    db_team = Team(**team.dict())
    db.add(db_team)
    db.commit()
    db.refresh(db_team)
    return db_team

@router.get("/", response_model=TeamPaginationResponse)
def read_teams(
    skip: int = 0,
    limit: int = 100,
    name: Optional[str] = None,
    db: Session = Depends(get_db),
    user_data=Depends(PermissionChecker(["team.read"], check_tenant=True))
):
    query = db.query(Team)
    
    # Apply filters
    if name:
        query = query.filter(Team.name.ilike(f"%{name}%"))
    
    total, items = paginate_query(query, skip, limit)
    return {"total": total, "items": items}

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

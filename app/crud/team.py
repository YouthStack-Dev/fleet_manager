from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models import Team
from app.schemas.team import TeamCreate, TeamUpdate
from app.crud.base import CRUDBase


class CRUDTeam(CRUDBase[Team, TeamCreate, TeamUpdate]):
    def get_by_id(self, db: Session, *, team_id: int) -> Optional[Team]:
        """Get team by primary key"""
        return db.query(Team).filter(Team.team_id == team_id).first()

    def get_by_name(self, db: Session, *, tenant_id: int, name: str) -> Optional[Team]:
        """Get team by name scoped to tenant"""
        return (
            db.query(Team)
            .filter(and_(Team.tenant_id == tenant_id, Team.name == name))
            .first()
        )

    def create(self, db: Session, *, obj_in: TeamCreate) -> Team:
        """Create a new team"""
        db_obj = Team(
            tenant_id=obj_in.tenant_id,
            name=obj_in.name,
            description=obj_in.description
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self, db: Session, *, db_obj: Team, obj_in: Union[TeamUpdate, Dict[str, Any]]
    ) -> Team:
        """Update team"""
        update_data = obj_in if isinstance(obj_in, dict) else obj_in.dict(exclude_unset=True)
        return super().update(db, db_obj=db_obj, obj_in=update_data)

    def get_all(
        self, db: Session, *, tenant_id: int, skip: int = 0, limit: int = 100
    ) -> List[Team]:
        """Get all teams for a tenant"""
        return (
            db.query(Team)
            .filter(Team.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count(self, db: Session, *, tenant_id: int) -> int:
        """Count teams per tenant"""
        return db.query(Team).filter(Team.tenant_id == tenant_id).count()


team_crud = CRUDTeam(Team)

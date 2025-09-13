from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.models.weekoff_config import WeekoffConfig
from app.schemas.weekoff_config import WeekoffConfigCreate, WeekoffConfigUpdate, WeekoffConfigResponse, WeekoffConfigPaginationResponse
from app.utils.pagination import paginate_query

router = APIRouter(prefix="/weekoff-configs", tags=["weekoff configs"])

@router.post("/", response_model=WeekoffConfigResponse, status_code=status.HTTP_201_CREATED)
def create_weekoff_config(weekoff_config: WeekoffConfigCreate, db: Session = Depends(get_db)):
    # Check if config already exists for this employee
    existing_config = db.query(WeekoffConfig).filter(WeekoffConfig.employee_id == weekoff_config.employee_id).first()
    if existing_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Weekoff config already exists for employee ID {weekoff_config.employee_id}"
        )

    db_weekoff_config = WeekoffConfig(**weekoff_config.dict())
    db.add(db_weekoff_config)
    db.commit()
    db.refresh(db_weekoff_config)
    return db_weekoff_config

@router.get("/", response_model=WeekoffConfigPaginationResponse)
def read_weekoff_configs(
    skip: int = 0,
    limit: int = 100,
    employee_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(WeekoffConfig)
    
    # Apply filters
    if employee_id:
        query = query.filter(WeekoffConfig.employee_id == employee_id)
    
    total, items = paginate_query(query, skip, limit)
    return {"total": total, "items": items}

@router.get("/{weekoff_id}", response_model=WeekoffConfigResponse)
def read_weekoff_config(weekoff_id: int, db: Session = Depends(get_db)):
    db_weekoff_config = db.query(WeekoffConfig).filter(WeekoffConfig.weekoff_id == weekoff_id).first()
    if not db_weekoff_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Weekoff Config with ID {weekoff_id} not found"
        )
    return db_weekoff_config

@router.get("/employee/{employee_id}", response_model=WeekoffConfigResponse)
def read_weekoff_config_by_employee(employee_id: int, db: Session = Depends(get_db)):
    db_weekoff_config = db.query(WeekoffConfig).filter(WeekoffConfig.employee_id == employee_id).first()
    if not db_weekoff_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Weekoff Config for employee ID {employee_id} not found"
        )
    return db_weekoff_config

@router.put("/{weekoff_id}", response_model=WeekoffConfigResponse)
def update_weekoff_config(weekoff_id: int, weekoff_config_update: WeekoffConfigUpdate, db: Session = Depends(get_db)):
    db_weekoff_config = db.query(WeekoffConfig).filter(WeekoffConfig.weekoff_id == weekoff_id).first()
    if not db_weekoff_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Weekoff Config with ID {weekoff_id} not found"
        )
    
    update_data = weekoff_config_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_weekoff_config, key, value)
    
    db.commit()
    db.refresh(db_weekoff_config)
    return db_weekoff_config

@router.delete("/{weekoff_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_weekoff_config(weekoff_id: int, db: Session = Depends(get_db)):
    db_weekoff_config = db.query(WeekoffConfig).filter(WeekoffConfig.weekoff_id == weekoff_id).first()
    if not db_weekoff_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Weekoff Config with ID {weekoff_id} not found"
        )
    
    db.delete(db_weekoff_config)
    db.commit()
    return None

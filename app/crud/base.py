from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import inspect

from app.database.session import Base

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    Base class for CRUD operations.
    """
    def __init__(self, model: Type[ModelType]):
        """
        Initialize with the model class
        """
        self.model = model

    def get(self, db: Session, id: Any) -> Optional[ModelType]:
        """
        Get an object by ID
        """
        # Get the primary key column name
        primary_key = inspect(self.model).primary_key[0].name
        return db.query(self.model).filter(getattr(self.model, primary_key) == id).first()

    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 100, filters: Dict = None) -> List[ModelType]:
        """
        Get multiple objects with optional filters
        """
        query = db.query(self.model)
        
        # Apply filters if provided
        if filters:
            for attr, value in filters.items():
                if hasattr(self.model, attr):
                    if isinstance(value, list):
                        query = query.filter(getattr(self.model, attr).in_(value))
                    else:
                        query = query.filter(getattr(self.model, attr) == value)
        
        return query.offset(skip).limit(limit).all()

    def create(self, db: Session, *, obj_in: CreateSchemaType) -> ModelType:
        """
        Create a new object
        """
        obj_in_data = jsonable_encoder(obj_in)
        db_obj = self.model(**obj_in_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, *, db_obj: ModelType, obj_in: Union[UpdateSchemaType, Dict[str, Any]]) -> ModelType:
        """
        Update an object
        """
        obj_data = jsonable_encoder(db_obj)
        
        # If obj_in is a dict, use it directly; otherwise convert to dict
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.dict(exclude_unset=True)
            
        # Update the object attributes
        for field in obj_data:
            if field in update_data:
                setattr(db_obj, field, update_data[field])
                
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def remove(self, db: Session, *, id: Any) -> ModelType:
        """
        Remove an object
        """
        # Get the primary key column name
        primary_key = inspect(self.model).primary_key[0].name
        
        obj = db.query(self.model).filter(getattr(self.model, primary_key) == id).first()
        db.delete(obj)
        db.commit()
        return obj

    def count(self, db: Session, *, filters: Dict = None) -> int:
        """
        Count objects with optional filters
        """
        query = db.query(self.model)
        
        # Apply filters if provided
        if filters:
            for attr, value in filters.items():
                if hasattr(self.model, attr):
                    if isinstance(value, list):
                        query = query.filter(getattr(self.model, attr).in_(value))
                    else:
                        query = query.filter(getattr(self.model, attr) == value)
        
        return query.count()

import re
from typing import Any, Dict, List, Optional, Type, TypeVar
from fastapi import HTTPException, status
from pydantic import BaseModel
from app.schemas.base import (
    BaseResponse, 
    ErrorResponse, 
    PaginatedResponse, 
    SuccessResponse,
    create_success_response,
    create_error_response,
    create_paginated_response
)

T = TypeVar('T', bound=BaseModel)

class ResponseWrapper:
    """Utility class for wrapping responses in standard format"""
    
    @staticmethod
    def success(data: Any = None, message: str = "Success") -> Dict[str, Any]:
        """Wrap successful response"""
        return create_success_response(data, message)
    
    @staticmethod
    def error(message: str, error_code: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Wrap error response"""
        return create_error_response(message, error_code, details)
    
    @staticmethod
    def paginated(
        items: List[Any], 
        total: int, 
        page: int = 1, 
        per_page: int = 10, 
        message: str = "Success"
    ) -> Dict[str, Any]:
        """Wrap paginated response"""
        return create_paginated_response(items, total, page, per_page, message)
    
    @staticmethod
    def created(data: Any = None, message: str = "Resource created successfully") -> Dict[str, Any]:
        """Wrap creation response"""
        return create_success_response(data, message)
    
    @staticmethod
    def updated(data: Any = None, message: str = "Resource updated successfully") -> Dict[str, Any]:
        """Wrap update response"""
        return create_success_response(data, message)
    
    @staticmethod
    def deleted(message: str = "Resource deleted successfully") -> Dict[str, Any]:
        """Wrap deletion response"""
        return create_success_response(None, message)

def handle_db_error(error: Exception) -> HTTPException:
    """Convert database errors to HTTP exceptions with detailed info"""
    error_msg = str(error)

    if "duplicate key" in error_msg.lower():
        # Extract the field that caused the unique constraint
        match = re.search(r'Key \((.*?)\)=\((.*?)\)', error_msg)
        field_info = {}
        if match:
            columns = match.group(1).split(", ")
            values = match.group(2).split(", ")
            field_info = {col: val for col, val in zip(columns, values)}

        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ResponseWrapper.error(
                message="Resource already exists with the same values",
                error_code="DUPLICATE_RESOURCE",
                details={"db_error": error_msg, "conflicting_fields": field_info}
            )
        )
    elif "foreign key" in error_msg.lower():
        match = re.search(r'Key \((.*?)\)=\((.*?)\)', error_msg)
        field_info = {}
        if match:
            columns = match.group(1).split(", ")
            values = match.group(2).split(", ")
            field_info = {col: val for col, val in zip(columns, values)}
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ResponseWrapper.error(
                message="Referenced resource not found",
                error_code="FOREIGN_KEY_VIOLATION",
                details={"db_error": error_msg ,"conflicting_fields": field_info}
            )
        )
    else:
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message="Database operation failed",
                error_code="DATABASE_ERROR",
                details={"db_error": error_msg}
            )
        )

def validate_pagination_params(skip: int, limit: int) -> tuple[int, int]:
    """Validate and normalize pagination parameters"""
    if skip < 0:
        skip = 0
    if limit <= 0 or limit > 100:
        limit = 10
    
    page = (skip // limit) + 1
    per_page = limit
    
    return page, per_page

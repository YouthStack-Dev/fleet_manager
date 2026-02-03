from typing import Any, Dict, Generic, List, Optional, TypeVar
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# India Standard Time
IST = ZoneInfo("Asia/Kolkata")

# Generic type for data payload
DataType = TypeVar('DataType')

class BaseResponse(BaseModel, Generic[DataType]):
    """
    Base response schema for all API endpoints
    """
    success: bool = Field(True, description="Indicates if the request was successful")
    message: str = Field("Success", description="Human readable message")
    data: Optional[DataType] = Field(None, description="Response data payload")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(IST), description="Response timestamp in IST")
    
    model_config = ConfigDict()

class ErrorResponse(BaseModel):
    """
    Error response schema for failed requests
    """
    success: bool = Field(False, description="Always false for error responses")
    message: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Specific error code")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(IST), description="Error timestamp in IST")
    
    model_config = ConfigDict()

class PaginationMeta(BaseModel):
    """
    Pagination metadata
    """
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_prev: bool = Field(..., description="Whether there is a previous page")

class PaginatedResponse(BaseModel, Generic[DataType]):
    """
    Paginated response schema
    """
    success: bool = Field(True, description="Indicates if the request was successful")
    message: str = Field("Success", description="Human readable message")
    data: List[DataType] = Field(..., description="List of items")
    meta: PaginationMeta = Field(..., description="Pagination metadata")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(IST), description="Response timestamp in IST")
    
    model_config = ConfigDict()

class SuccessResponse(BaseModel):
    """
    Simple success response for operations that don't return data
    """
    success: bool = Field(True, description="Indicates if the request was successful")
    message: str = Field("Operation completed successfully", description="Success message")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(IST), description="Response timestamp in IST")
    
    model_config = ConfigDict()

# Utility functions for creating consistent responses
def create_success_response(data: Any = None, message: str = "Success") -> Dict[str, Any]:
    """Create a success response with IST timestamp"""
    return {
        "success": True,
        "message": message,
        "data": data,
        "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    }

def create_error_response(message: str, error_code: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create an error response with IST timestamp"""
    return {
        "success": False,
        "message": message,
        "error_code": error_code,
        "details": details,
        "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    }

def create_paginated_response(
    items: List[Any], 
    total: int, 
    page: int, 
    per_page: int, 
    message: str = "Success"
) -> Dict[str, Any]:
    """Create a paginated response with IST timestamp"""
    total_pages = (total + per_page - 1) // per_page
    
    return {
        "success": True,
        "message": message,
        "data": items,
        "meta": {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        },
        "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    }

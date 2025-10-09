import os
import io
import shutil
from pathlib import Path
from typing import Optional, List
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from app.utils.response_utils import ResponseWrapper, handle_db_error, handle_http_error
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Root directories
ROOT_DIR = Path(__file__).resolve().parent.parent.parent  # adjust if needed
UPLOADS_DIR = ROOT_DIR / "uploaded_files"


async def file_size_validator(
    file: Optional[UploadFile], 
    allowed_types: List[str], 
    max_size_mb: int, 
    required: bool = True
) -> Optional[UploadFile]:
    """
    Validate file size and type.
    
    Args:
        file: Uploaded file
        allowed_types: List of allowed MIME types
        max_size_mb: Maximum file size in MB
        required: Whether file is required
        
    Returns:
        UploadFile: Validated file or None
    """
    if not file or not file.filename:
        if required:
            raise HTTPException(status_code=400, detail="File is required")
        return None
    
    # Check file type
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400, 
            detail=f"File type {file.content_type} not allowed. Allowed types: {allowed_types}"
        )
    
    # Check file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset to beginning
    
    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=400, 
            detail=f"File size {file_size} bytes exceeds maximum allowed size of {max_size_mb}MB"
        )
    
    return file

def save_file(file: Optional[UploadFile], vendor_id: int, rc_number: str, file_type: str) -> Optional[str]:
    """
    Legacy function - now redirects to storage service.
    This maintains backward compatibility.
    """
    if not file:
        return None
        
    from app.services.storage_service import storage_service
    return storage_service.save_file(file, vendor_id, rc_number, file_type)

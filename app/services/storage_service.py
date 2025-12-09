import os
import uuid
from datetime import datetime
from typing import Optional, BinaryIO
from pathlib import Path
from fastapi import UploadFile, HTTPException
import fsspec
import tempfile
from app.config import settings
from app.core.logging_config import get_logger
from common_utils import get_current_ist_time

logger = get_logger(__name__)

class StorageService:
    """
    Unified storage service supporting local filesystem and cloud storage.
    Uses fsspec for abstraction - easily migrate from local to S3/GCS/Azure.
    
    Environment-aware:
    - development: Uses local ./local_storage directory (your machine)
    - dev-server: Uses dev server filesystem at /var/lib/fleet/dev-storage (Linux dev server)  
    - production: Uses production filesystem or cloud storage (S3/GCS/Azure)
    """
    
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or settings.STORAGE_BASE_URL
        self.storage_type = settings.STORAGE_TYPE
        self.environment = settings.ENV
        
        logger.info(f"StorageService initialized: env={self.environment}, type={self.storage_type}, url={self.base_url}")
        self._ensure_storage_directory()
    
    def _ensure_storage_directory(self):
        """Ensure storage directory exists for filesystem storage"""
        if self.base_url.startswith("file://"):
            local_path = self.base_url.replace("file://", "")
            
            try:
                # Create directory with parents if it doesn't exist
                Path(local_path).mkdir(parents=True, exist_ok=True)
                
                # Set secure permissions for filesystem storage
                if os.name != 'nt':  # Skip chmod on Windows
                    if self.environment == "development":
                        # More relaxed permissions for local development
                        os.chmod(local_path, 0o755)
                    else:
                        # Secure permissions for server environments
                        os.chmod(local_path, 0o750)
                
                logger.info(f"Storage directory ensured: {local_path} (env: {self.environment})")
                
                # Test write permissions
                test_file = Path(local_path) / ".storage_test"
                test_file.touch()
                test_file.unlink()
                logger.info(f"Storage directory is writable: {local_path}")
                
            except Exception as e:
                logger.error(f"Failed to setup storage directory {local_path}: {e}")
                raise HTTPException(status_code=500, detail=f"Storage setup failed: {e}")
        else:
            # Cloud storage - no local directory setup needed
            logger.info(f"Using cloud storage: {self.base_url}")
    
    def _generate_filename(self, vendor_id: int, rc_number: str, file_type: str, original_filename: str) -> str:
        """Generate secure filename with timestamp and UUID"""
        timestamp = get_current_ist_time().strftime("%Y%m%d_%H%M%S")
        file_extension = os.path.splitext(original_filename)[1].lower()
        unique_id = str(uuid.uuid4())[:8]
        
        # Clean RC number for safe filename
        safe_rc_number = "".join(c for c in rc_number if c.isalnum() or c in "-_")
        
        return f"vendor_{vendor_id}/vehicle_{safe_rc_number}/{file_type}/{timestamp}_{unique_id}{file_extension}"
    
    def save_file(
        self, 
        file: UploadFile, 
        vendor_id: int, 
        rc_number: str, 
        file_type: str
    ) -> str:
        """
        Save file to storage and return the file URL/path.
        """
        try:
            if not file or not file.filename:
                return None
                
            filename = self._generate_filename(vendor_id, rc_number, file_type, file.filename)
            file_url = f"{self.base_url}/{filename}"
            
            logger.info(f"Saving file: {file.filename} -> {filename} (env: {self.environment})")
            
            # Read file content
            file.file.seek(0)
            content = file.file.read()
            
            if len(content) == 0:
                logger.warning(f"Empty file received: {file.filename}")
                return None
            
            # Save using fsspec (works for local, S3, GCS, Azure, etc.)
            with fsspec.open(file_url, "wb") as f:
                f.write(content)
            
            logger.info(f"File saved successfully: {filename} ({len(content)} bytes)")
            return filename  # Return relative path for database
            
        except Exception as e:
            logger.error(f"Error saving file {file.filename}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    def get_file_url(self, file_path: str) -> str:
        """Get full URL for a stored file"""
        if not file_path:
            return None
        return f"{self.base_url}/{file_path}"
    
    def delete_file(self, file_path: str) -> bool:
        """Delete a file from storage"""
        try:
            if not file_path:
                return True
                
            file_url = f"{self.base_url}/{file_path}"
            fs = fsspec.filesystem(file_url.split("://")[0])
            
            if fs.exists(file_url):
                fs.rm(file_url)
                logger.info(f"File deleted: {file_path}")
            else:
                logger.warning(f"File not found for deletion: {file_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {str(e)}")
            return False
    
    def file_exists(self, file_path: str) -> bool:
        """Check if file exists in storage"""
        try:
            if not file_path:
                return False
                
            file_url = f"{self.base_url}/{file_path}"
            fs = fsspec.filesystem(file_url.split("://")[0])
            return fs.exists(file_url)
            
        except Exception as e:
            logger.error(f"Error checking file existence {file_path}: {str(e)}")
            return False

    def get_file_content(self, file_path: str) -> bytes:
        """Get file content as bytes"""
        try:
            if not file_path:
                return None
                
            file_url = f"{self.base_url}/{file_path}"
            
            with fsspec.open(file_url, "rb") as f:
                content = f.read()
            
            logger.info(f"File content read: {file_path} ({len(content)} bytes)")
            return content
            
        except Exception as e:
            logger.error(f"Error reading file content {file_path}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    def get_temp_file_path(self, file_path: str) -> str:
        """
        Download file to temporary location and return temp file path.
        Useful for serving cloud files via FileResponse.
        """
        try:
            if not file_path:
                return None
                
            file_url = f"{self.base_url}/{file_path}"
            
            # Get file extension for temp file
            file_extension = os.path.splitext(file_path)[1]
            
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
            
            # Download content to temp file
            with fsspec.open(file_url, "rb") as src:
                temp_file.write(src.read())
            
            temp_file.close()
            
            logger.info(f"File downloaded to temp: {file_path} -> {temp_file.name}")
            return temp_file.name
            
        except Exception as e:
            logger.error(f"Error creating temp file for {file_path}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to prepare file: {str(e)}")

    def get_storage_info(self) -> dict:
        """Get information about current storage configuration"""
        return {
            "environment": self.environment,
            "storage_type": self.storage_type,
            "base_url": self.base_url,
            "is_filesystem": self.base_url.startswith("file://"),
            "is_cloud": not self.base_url.startswith("file://"),
            "is_local_dev": self.environment == "development",
            "is_dev_server": self.environment == "dev-server",
            "is_production": self.environment == "production"
        }

# Global storage service instance
storage_service = StorageService()

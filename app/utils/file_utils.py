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
    file: UploadFile,
    allowed_types: List[str],
    max_size_mb: int = 5,
    required: bool = True
) -> UploadFile:
    """
    Validate uploaded file for type, size, and presence.
    Used before saving driver or document uploads.
    """
    try:
        if not file or not file.filename:
            if required:
                logger.error("File missing for required upload")
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=ResponseWrapper.error(
                        message="File is required but not provided",
                        error_code="FILE_REQUIRED"
                    ),
                )
            return None

        logger.debug(f"Validating file: {file.filename}, content_type={file.content_type}")

        if file.content_type not in allowed_types:
            logger.warning(
                f"Invalid content type '{file.content_type}' for file '{file.filename}'. "
                f"Allowed: {allowed_types}"
            )
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=ResponseWrapper.error(
                    message=f"Invalid file type '{file.content_type}'. Allowed: {allowed_types}",
                    error_code="INVALID_FILE_TYPE",
                ),
            )

        contents = await file.read()
        size_mb = len(contents) / (1024 * 1024)
        if size_mb > max_size_mb:
            logger.warning(
                f"File '{file.filename}' exceeds size limit: {size_mb:.2f}MB > {max_size_mb}MB"
            )
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=ResponseWrapper.error(
                    message=f"File '{file.filename}' too large (max {max_size_mb}MB)",
                    error_code="FILE_TOO_LARGE",
                ),
            )

        # Reset stream so downstream save functions can read again
        file.file = io.BytesIO(contents)
        logger.debug(f"File '{file.filename}' validation passed ({size_mb:.2f}MB)")
        return file

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error validating file '{getattr(file, 'filename', 'unknown')}': {e}")
        raise handle_http_error(e)


def save_file(
    file: Optional[UploadFile],
    vendor_id: int,
    driver_code: str,
    doc_type: str
) -> Optional[str]:
    """
    Save a validated file to structured storage and return relative path.
    Path: /uploaded_files/vendors/{vendor_id}/drivers/{driver_code}/{doc_type}/{driver_code}_{doc_type}.{ext}
    """
    try:
        if not file or not file.filename:
            logger.debug(f"No file provided for {doc_type}, skipping save.")
            return None

        # Determine extension and filename
        _, ext = os.path.splitext(file.filename)
        ext = ext.lower().strip()
        safe_filename = f"{driver_code.strip()}_{doc_type.strip()}{ext}"

        # Build target folder path
        folder_path = UPLOADS_DIR / "vendors" / str(vendor_id) / "drivers" / driver_code.strip() / doc_type
        folder_path.mkdir(parents=True, exist_ok=True)

        file_path = folder_path / safe_filename

        # Save file to disk
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Compute relative path for API response
        relative_path = file_path.relative_to(ROOT_DIR)
        clean_path = str(relative_path).replace("\\", "/")

        logger.info(
            f"File '{doc_type}' uploaded successfully for driver={driver_code}, vendor={vendor_id}, path={clean_path}"
        )
        if file_path.exists():
            logger.info(f"[DEBUG] File exists on disk: {file_path.resolve()}")
        else:
            logger.warning(f"[DEBUG] File not found on disk: {file_path.resolve()}")

        return clean_path

    except OSError as e:
        logger.exception(f"OS error saving file '{file.filename}' for driver={driver_code}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ResponseWrapper.error(
                message=f"Failed to save '{file.filename}'. Disk write error.",
                error_code="FILE_SAVE_ERROR",
            ),
        )

    except SQLAlchemyError as e:
        logger.exception(f"Database error during file save for driver={driver_code}: {e}")
        raise handle_db_error(e)

    except Exception as e:
        logger.exception(f"Unexpected error while saving file '{file.filename}': {e}")
        raise handle_http_error(e)

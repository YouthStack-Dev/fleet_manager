from datetime import datetime, date
from fastapi import HTTPException , status

from app.utils.response_utils import ResponseWrapper

def validate_future_dates(fields: dict, context: str = "vehicle"):
    today = date.today()

    for name, value in fields.items():
        if not value:
            continue

        # Normalize value → date object
        if isinstance(value, datetime):
            value = value.date()
        elif isinstance(value, str):
            try:
                # Parse ISO or 'YYYY-MM-DD' formats
                value = datetime.fromisoformat(value).date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ResponseWrapper.error(
                        message=f"Invalid date format for {name.replace('_', ' ').title()} in {context}. Expected YYYY-MM-DD.",
                        error_code="INVALID_DATE_FORMAT",
                    ),
                )

        # Compare after normalization
        if value <= today:
            field_label = name.replace("_", " ").title()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ResponseWrapper.error(
                    message=f"{field_label} in {context} must be a future date.",
                    error_code="INVALID_DATE",
                ),
            )

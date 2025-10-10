from datetime import date
from fastapi import HTTPException , status

from app.utils.response_utils import ResponseWrapper


def validate_future_dates(fields: dict, context: str = "vehicle"):
    today = date.today()
    for name, value in fields.items():
        if value and value <= today:
            field_label = name.replace("_", " ").title()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                    detail=ResponseWrapper.error(
                        message="{field_label} must be a future date".format(field_label=field_label),
                        error_code="INVALID_DATE",
                    ),
            )
"""
Shared Python enums used across SQLAlchemy models.

Import from here instead of defining GenderEnum (and similar) separately
in each model file — they must be the *same* Python class so that equality
checks and SQLAlchemy Enum column introspection work correctly across tables.
"""
from enum import Enum as PyEnum


class GenderEnum(str, PyEnum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"


class FemaleConstraintEnum(str, PyEnum):
    """
    Shift-level rule controlling when an escort is deployed for female passengers.

    FIRST_LAST_FEMALE       – escort required if the first OR last stop has a female employee
    SECOND_SECOND_LAST_FEMALE – escort required if the 2nd OR 2nd-last stop has a female employee
    ANY_FEMALE              – escort required if ANY female is on the route
    DISABLE                 – never deploy an escort for this shift (overrides tenant config)
    """
    FIRST_LAST_FEMALE = "First/Last Female"
    SECOND_SECOND_LAST_FEMALE = "Second/Second Last Female"
    ANY_FEMALE = "Any Female"
    DISABLE = "Disable"

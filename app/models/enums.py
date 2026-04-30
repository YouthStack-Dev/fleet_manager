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

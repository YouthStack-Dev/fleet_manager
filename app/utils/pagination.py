from typing import Tuple, List, TypeVar, Generic, Any
from sqlalchemy.orm import Query

T = TypeVar('T')

def paginate_query(query: Query, skip: int = 0, limit: int = 100) -> Tuple[int, List[Any]]:
    """
    Helper function to paginate SQLAlchemy queries.
    Returns a tuple of (total_count, items)
    """
    total = query.count()
    items = query.offset(skip).limit(limit).all()
    return total, items

"""
Shared FastAPI dependencies.
"""
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db

# Re-export get_db as a typed dependency
DBSession = Annotated[AsyncSession, Depends(get_db)]


def require_admin(request: Request) -> None:
    """
    Verifies that the admin session cookie is set.
    Raises 401 if not authenticated. Used on admin API routes.
    For admin HTML pages, the check is done in the route handler
    to redirect to the login page instead.
    """
    if not request.session.get("admin_authenticated"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required",
        )

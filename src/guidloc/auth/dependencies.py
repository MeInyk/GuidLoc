"""FastAPI dependencies for authentication."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.auth.jwt import InvalidTokenError, TokenExpiredError, decode_access_token
from guidloc.common.database import get_session
from guidloc.users.models import User
from guidloc.users.service import get_user_by_id

bearer_scheme = HTTPBearer(auto_error=False, bearerFormat="JWT")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Resolve the authenticated user from a Bearer token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None or not credentials.credentials:
        raise credentials_exception

    try:
        payload = decode_access_token(credentials.credentials)
    except (TokenExpiredError, InvalidTokenError) as exc:
        raise credentials_exception from exc

    subject = payload.get("sub")
    if not subject:
        raise credentials_exception

    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise credentials_exception from exc

    user = await get_user_by_id(session, user_id)
    if user is None:
        raise credentials_exception

    return user

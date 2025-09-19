from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .utils import verify_token

class JWTAuthMiddleware(HTTPBearer):
    def __init__(self, auto_error: bool = True):
        super(JWTAuthMiddleware, self).__init__(auto_error=auto_error)
        
    async def __call__(self, request: Request):
        credentials: HTTPAuthorizationCredentials = await super(JWTAuthMiddleware, self).__call__(request)
        
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid authorization code"
            )
        
        try:
            # Verify token and get user data
            payload = verify_token(credentials.credentials)
            request.state.user = payload
            return payload, credentials.credentials
        except HTTPException as e:
            # If token verification fails, raise HTTPException
            raise e
        except Exception as e:
            # Handle other exceptions
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
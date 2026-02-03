"""
Push Notification Router - Device token management and push notification endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Dict, Any
from app.database.session import get_db
from app.schemas.push_notification import (
    DeviceTokenRequest,
    DeviceTokenResponse,
    PushNotificationRequest,
    BatchPushNotificationRequest,
    SessionInfoResponse,
    NotificationResult
)
from app.services.session_manager import SessionManager
from app.services.session_cache import SessionCache
from app.services.unified_notification_service import UnifiedNotificationService
from app.core.logging_config import get_logger
from app.config import settings
from common_utils.auth.utils import verify_token

logger = get_logger(__name__)

router = APIRouter(prefix="/push-notifications", tags=["Push Notifications"])
security = HTTPBearer()


def get_redis_client():
    """Dependency to get Redis client"""
    import redis
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
        decode_responses=True,
        socket_timeout=5
    )


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    ✅ SECURE: Extract and verify current user from JWT token
    
    This is the KEY security function that prevents token spoofing!
    
    How it works:
    1. Client sends JWT token in Authorization header: "Bearer <token>"
    2. We decode and verify the JWT signature (proves it's from our server)
    3. Extract user_id, user_type, tenant_id from VERIFIED JWT claims
    4. Return verified user info (client CANNOT fake this)
    
    Security:
    - JWT is cryptographically signed with SECRET_KEY
    - Only our server can create valid JWTs
    - Client cannot modify claims without breaking signature
    - Expired tokens are automatically rejected
    
    Example JWT payload:
    {
        "user_id": 123,
        "user_type": "employee",
        "tenant_id": 1,
        "exp": 1704384000  # Expiration timestamp
    }
    """
    try:
        # Decode JWT and verify signature
        # This proves the token was issued by our auth system
        payload = verify_token(credentials.credentials)
        
        # Extract verified user information from JWT claims
        user_id = payload.get("user_id")
        user_type = payload.get("user_type", "employee")
        tenant_id = payload.get("tenant_id")
        
        if not user_id or not tenant_id:
            logger.error(f"[push_notifications] Invalid JWT payload: missing user_id or tenant_id")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing required claims"
            )
        
        logger.debug(
            f"[push_notifications] Authenticated user: {user_type}:{user_id}, tenant:{tenant_id}"
        )
        
        return {
            "user_id": user_id,
            "user_type": user_type,
            "tenant_id": tenant_id
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions from verify_token (expired, invalid, etc.)
        raise
    except Exception as e:
        logger.error(f"[push_notifications] Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )


@router.post("/register-token", response_model=DeviceTokenResponse, status_code=status.HTTP_201_CREATED)
async def register_device_token(
    token_data: DeviceTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
    redis_client = Depends(get_redis_client),
    current_user: Dict[str, Any] = Depends(get_current_user)  # ✅ SECURE: JWT authentication required
):
    """
    🔐 Register FCM device token for push notifications
    
    **SECURITY**: Requires valid JWT token in Authorization header
    User identity (user_id, user_type, tenant_id) is extracted from verified JWT - client cannot fake this!
    
    Works for all user types: admin, employee, vendor, driver
    Automatically enforces single active session per platform
    
    Request Body:
    - **fcm_token**: Firebase Cloud Messaging token from client device
    - **platform**: 'web' or 'app' 
    - **device_type**: Optional device type (ios, android, chrome, etc.)
    - **device_id**: Optional unique device fingerprint
    - **app_version**: Optional app version string
    - **device_model**: Optional device model name
    
    Headers Required:
    - **Authorization**: Bearer <jwt_token>
    
    How Authentication Works:
    1. Client logs in via /auth/login, receives JWT token
    2. JWT contains: {user_id: 123, user_type: "employee", tenant_id: 1}
    3. Client sends JWT in this request
    4. Server verifies JWT signature and extracts user info
    5. We register FCM token for the VERIFIED user (not what client claims)
    
    Security Benefits:
    - ✅ Client cannot pretend to be another user
    - ✅ Client cannot register tokens for admin accounts
    - ✅ Client cannot register tokens for other tenants
    - ✅ Expired/invalid tokens are automatically rejected
    """
    try:
        # ✅ IMPORTANT: current_user comes from JWT (server-verified)
        # NOT from request body - client cannot fake this!
        
        logger.info(
            f"[push_notifications] Token registration request: "
            f"{current_user['user_type']}:{current_user['user_id']}, "
            f"platform={token_data.platform}"
        )
        
        # Build device info
        device_info = {
            "device_type": token_data.device_type,
            "device_id": token_data.device_id,
            "app_version": token_data.app_version,
            "device_model": token_data.device_model,
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("User-Agent")
        }
        
        # Register session
        cache = SessionCache(redis_client)
        session_manager = SessionManager(db, cache)
        
        session = session_manager.register_session(
            user_type=current_user["user_type"],
            user_id=current_user["user_id"],
            tenant_id=current_user["tenant_id"],
            platform=token_data.platform,
            fcm_token=token_data.fcm_token,
            device_info=device_info
        )
        
        logger.info(
            f"[push_notifications] Token registered successfully: "
            f"session_id={session.session_id}, {current_user['user_type']}:{current_user['user_id']}"
        )
        
        return DeviceTokenResponse(
            success=True,
            message="Device token registered successfully",
            session_id=session.session_id
        )
        
    except ValueError as e:
        logger.error(f"[push_notifications] Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"[push_notifications] Error registering token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register device token"
        )


@router.post("/logout", response_model=DeviceTokenResponse)
async def logout_device(
    request: Request,
    platform: str = None,
    db: Session = Depends(get_db),
    redis_client = Depends(get_redis_client),
    current_user: Dict[str, Any] = Depends(get_current_user)  # ✅ JWT auth required
):
    """
    🔐 Logout (deactivate) device session for push notifications
    
    **SECURITY**: Requires valid JWT token - can only logout your own devices
    
    Query Parameters:
    - **platform**: Optional - 'web' or 'app'. If not provided, logs out all platforms
    
    Headers Required:
    - **Authorization**: Bearer <jwt_token>
    """
    try:
        # ✅ current_user verified from JWT
        
        logger.info(
            f"[push_notifications] Logout request: "
            f"{current_user['user_type']}:{current_user['user_id']}, "
            f"platform={platform or 'all'}"
        )
        
        # Logout session
        cache = SessionCache(redis_client)
        session_manager = SessionManager(db, cache)
        
        success = session_manager.logout_session(
            user_type=current_user["user_type"],
            user_id=current_user["user_id"],
            platform=platform
        )
        
        if success:
            logger.info(
                f"[push_notifications] Logout successful: "
                f"{current_user['user_type']}:{current_user['user_id']}"
            )
            return DeviceTokenResponse(
                success=True,
                message="Device logged out successfully"
            )
        else:
            return DeviceTokenResponse(
                success=False,
                message="No active session found"
            )
        
    except Exception as e:
        logger.error(f"[push_notifications] Error during logout: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to logout device"
        )


@router.get("/session-info", response_model=SessionInfoResponse)
async def get_session_info(
    request: Request,
    db: Session = Depends(get_db),
    redis_client = Depends(get_redis_client),
    current_user: Dict[str, Any] = Depends(get_current_user)  # ✅ JWT auth required
):
    """
    🔐 Get session information for current user
    
    **SECURITY**: Requires valid JWT token - can only see your own sessions
    
    Returns all sessions (active and inactive) for the authenticated user
    
    Headers Required:
    - **Authorization**: Bearer <jwt_token>
    """
    try:
        # ✅ current_user verified from JWT
        
        cache = SessionCache(redis_client)
        session_manager = SessionManager(db, cache)
        
        info = session_manager.get_user_sessions_info(
            user_type=current_user["user_type"],
            user_id=current_user["user_id"]
        )
        
        return SessionInfoResponse(**info)
        
    except Exception as e:
        logger.error(f"[push_notifications] Error getting session info: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get session information"
        )


@router.post("/send", response_model=NotificationResult)
async def send_push_notification(
    notification: PushNotificationRequest,
    db: Session = Depends(get_db),
    redis_client = Depends(get_redis_client)
):
    """
    Send push notification to single user (Admin only)
    
    This endpoint is for admin/system use to send notifications programmatically
    """
    try:
        logger.info(
            f"[push_notifications] Send notification: "
            f"{notification.user_type}:{notification.user_id}"
        )
        
        cache = SessionCache(redis_client)
        service = UnifiedNotificationService(db, cache)
        
        result = service.send_to_user(
            user_type=notification.user_type,
            user_id=notification.user_id,
            title=notification.title,
            body=notification.body,
            data=notification.data,
            priority=notification.priority
        )
        
        if result["success"]:
            return NotificationResult(
                success=True,
                message="Notification sent successfully",
                success_count=1,
                failure_count=0
            )
        else:
            return NotificationResult(
                success=False,
                error=result.get("error"),
                message=result.get("message"),
                success_count=0,
                failure_count=1
            )
        
    except Exception as e:
        logger.error(f"[push_notifications] Error sending notification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send notification"
        )


@router.post("/send-batch", response_model=NotificationResult)
async def send_batch_push_notification(
    notification: BatchPushNotificationRequest,
    db: Session = Depends(get_db),
    redis_client = Depends(get_redis_client)
):
    """
    Send push notification to multiple users in batch (Admin only)
    
    High-performance batch sending:
    - 1 database query for N users
    - 1 FCM API call for up to 500 users
    - Automatic invalid token cleanup
    """
    try:
        logger.info(
            f"[push_notifications] Batch send notification: "
            f"{len(notification.recipients)} recipients"
        )
        
        cache = SessionCache(redis_client)
        service = UnifiedNotificationService(db, cache)
        
        result = service.send_to_users_batch(
            recipients=notification.recipients,
            title=notification.title,
            body=notification.body,
            data=notification.data,
            priority=notification.priority
        )
        
        return NotificationResult(
            success=result["success_count"] > 0,
            success_count=result["success_count"],
            failure_count=result["failure_count"],
            no_session_count=result["no_session_count"],
            message=f"Sent to {result['success_count']}/{len(notification.recipients)} recipients"
        )
        
    except Exception as e:
        logger.error(f"[push_notifications] Error in batch send: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send batch notifications"
        )


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check(redis_client = Depends(get_redis_client)):
    """
    Health check endpoint for push notification service
    
    Checks Redis connectivity
    """
    try:
        cache = SessionCache(redis_client)
        redis_healthy = cache.health_check()
        
        return {
            "status": "healthy" if redis_healthy else "degraded",
            "redis": "connected" if redis_healthy else "disconnected",
            "service": "push_notifications"
        }
    except Exception as e:
        logger.error(f"[push_notifications] Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "service": "push_notifications"
        }

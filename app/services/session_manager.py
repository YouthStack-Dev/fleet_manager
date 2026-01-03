"""
Session Manager - Unified session lifecycle management
Enforces single active session per user per platform
"""
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from app.models.user_session import UserSession
from app.services.session_cache import SessionCache
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class SessionManager:
    """
    Manages device session lifecycle for all user types
    
    Key Features:
    - Single active session per user per platform (database-enforced)
    - Automatic old session deactivation
    - Cache-first architecture
    - Batch operations support
    - Session health monitoring
    
    Business Rules:
    - User can have ONE active web session
    - User can have ONE active app session  
    - User CAN be logged in on both web AND app simultaneously
    - New login on same platform deactivates old session automatically
    """
    
    def __init__(self, db: Session, cache: Optional[SessionCache] = None):
        """
        Initialize Session Manager
        
        Args:
            db: SQLAlchemy database session
            cache: Optional SessionCache instance
        """
        self.db = db
        self.cache = cache or SessionCache()
        logger.debug("[session_manager] Initialized")
    
    def register_session(
        self,
        user_type: str,
        user_id: int,
        tenant_id: str,
        platform: str,
        fcm_token: str,
        device_info: Optional[Dict[str, Any]] = None
    ) -> UserSession:
        """
        Register new device session (enforces single active session per platform)
        
        Workflow:
        1. Validate inputs
        2. Deactivate old session on same platform (if exists)
        3. Create new active session
        4. Cache new session data
        5. Return session object
        
        Args:
            user_type: User type (admin, employee, vendor, driver)
            user_id: User ID
            tenant_id: Tenant ID
            platform: Platform (web or app)
            fcm_token: Firebase Cloud Messaging token
            device_info: Optional dict with device_type, device_id, app_version, etc.
            
        Returns:
            UserSession object
            
        Raises:
            ValueError: If invalid inputs
        """
        # Validate inputs
        if not UserSession.validate_user_type(user_type):
            raise ValueError(f"Invalid user_type: {user_type}")
        
        if not UserSession.validate_platform(platform):
            raise ValueError(f"Invalid platform: {platform}")
        
        if not fcm_token or len(fcm_token) < 140:
            raise ValueError(f"Invalid FCM token format")
        
        logger.info(
            f"[session_manager] Registering session: "
            f"{user_type}:{user_id}, platform={platform}, tenant={tenant_id}"
        )
        
        device_info = device_info or {}
        
        try:
            # Step 1: Deactivate old session on same platform
            old_session = self.db.query(UserSession).filter_by(
                user_type=user_type,
                user_id=user_id,
                platform=platform,
                is_active=True
            ).first()
            
            if old_session:
                old_session.is_active = False
                old_session.updated_at = datetime.utcnow()
                logger.info(
                    f"[session_manager] Deactivated old session: "
                    f"session_id={old_session.session_id}, token={old_session.fcm_token[:20]}..."
                )
                
                # Invalidate old session cache
                self.cache.invalidate_user(user_type, user_id)
                self.cache.invalidate_session(old_session.session_id)
            
            # Step 2: Create new active session
            new_session = UserSession(
                user_type=user_type,
                user_id=user_id,
                tenant_id=tenant_id,
                platform=platform,
                fcm_token=fcm_token,
                device_type=device_info.get("device_type"),
                device_id=device_info.get("device_id"),
                app_version=device_info.get("app_version"),
                device_model=device_info.get("device_model"),
                ip_address=device_info.get("ip_address"),
                user_agent=device_info.get("user_agent"),
                is_active=True,
                last_activity_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=30)
            )
            
            self.db.add(new_session)
            self.db.commit()
            self.db.refresh(new_session)
            
            logger.info(
                f"[session_manager] Created new session: "
                f"session_id={new_session.session_id}, token={fcm_token[:20]}..."
            )
            
            # Step 3: Cache new session data
            self.cache.set_token(user_type, user_id, fcm_token)
            self.cache.set_platform(user_type, user_id, platform)
            self.cache.set_session(new_session.session_id, new_session.to_dict())
            
            logger.info(f"[session_manager] Session registered successfully: {user_type}:{user_id}")
            
            return new_session
            
        except IntegrityError as e:
            self.db.rollback()
            logger.error(
                f"[session_manager] IntegrityError during session registration: {e}",
                exc_info=True
            )
            # This should not happen due to our deactivation logic, but handle it
            raise ValueError("Session registration failed due to constraint violation")
            
        except Exception as e:
            self.db.rollback()
            logger.error(
                f"[session_manager] Unexpected error during session registration: {e}",
                exc_info=True
            )
            raise
    
    def get_active_session(
        self,
        user_type: str,
        user_id: int,
        platform: Optional[str] = None
    ) -> Optional[UserSession]:
        """
        Get active session for user (cache-first)
        
        Args:
            user_type: User type
            user_id: User ID
            platform: Optional platform filter (web or app)
            
        Returns:
            UserSession object or None
        """
        try:
            # Build query
            query = self.db.query(UserSession).filter_by(
                user_type=user_type,
                user_id=user_id,
                is_active=True
            )
            
            if platform:
                query = query.filter_by(platform=platform)
            
            session = query.first()
            
            if session:
                logger.debug(
                    f"[session_manager] Active session found: "
                    f"{user_type}:{user_id}, platform={session.platform}"
                )
                
                # Update cache
                self.cache.set_token(user_type, user_id, session.fcm_token)
                self.cache.set_platform(user_type, user_id, session.platform)
            else:
                logger.debug(f"[session_manager] No active session: {user_type}:{user_id}")
            
            return session
            
        except Exception as e:
            logger.error(
                f"[session_manager] Error getting active session: {e}",
                exc_info=True
            )
            return None
    
    def get_active_sessions_batch(
        self,
        recipients: List[Dict[str, Any]]
    ) -> List[UserSession]:
        """
        Get active sessions for multiple users (batch query)
        
        Performance: 1 database query for N users
        
        Args:
            recipients: List of dicts with 'user_type' and 'user_id'
            
        Returns:
            List of UserSession objects
        """
        if not recipients:
            return []
        
        try:
            # Build list of (user_type, user_id) tuples
            user_keys = [(r["user_type"], r["user_id"]) for r in recipients]
            
            # Single query with IN clause
            sessions = self.db.query(UserSession).filter(
                UserSession.is_active == True,
                sa.tuple_(UserSession.user_type, UserSession.user_id).in_(user_keys)
            ).all()
            
            logger.info(
                f"[session_manager] Batch query: "
                f"requested={len(recipients)}, found={len(sessions)}"
            )
            
            # Update cache for found sessions
            for session in sessions:
                self.cache.set_token(session.user_type, session.user_id, session.fcm_token)
                self.cache.set_platform(session.user_type, session.user_id, session.platform)
            
            return sessions
            
        except Exception as e:
            logger.error(
                f"[session_manager] Error in batch query: {e}",
                exc_info=True
            )
            return []
    
    def update_last_activity(
        self,
        session_id: int
    ) -> bool:
        """
        Update session last_activity_at timestamp
        
        Args:
            session_id: Session ID
            
        Returns:
            True if updated successfully
        """
        try:
            session = self.db.query(UserSession).filter_by(session_id=session_id).first()
            
            if session:
                session.last_activity_at = datetime.utcnow()
                self.db.commit()
                
                logger.debug(f"[session_manager] Updated last_activity: session_id={session_id}")
                
                # Refresh cache TTL
                self.cache.set_token(session.user_type, session.user_id, session.fcm_token)
                self.cache.set_platform(session.user_type, session.user_id, session.platform)
                
                return True
            else:
                logger.warning(f"[session_manager] Session not found for activity update: {session_id}")
                return False
                
        except Exception as e:
            logger.error(
                f"[session_manager] Error updating last_activity: {e}",
                exc_info=True
            )
            self.db.rollback()
            return False
    
    def logout_session(
        self,
        user_type: str,
        user_id: int,
        platform: Optional[str] = None
    ) -> bool:
        """
        Logout (deactivate) user session
        
        Args:
            user_type: User type
            user_id: User ID
            platform: Optional platform (if None, deactivates all platforms)
            
        Returns:
            True if deactivated successfully
        """
        try:
            query = self.db.query(UserSession).filter_by(
                user_type=user_type,
                user_id=user_id,
                is_active=True
            )
            
            if platform:
                query = query.filter_by(platform=platform)
            
            sessions = query.all()
            
            if not sessions:
                logger.warning(
                    f"[session_manager] No active sessions to logout: "
                    f"{user_type}:{user_id}, platform={platform}"
                )
                return False
            
            # Deactivate sessions
            for session in sessions:
                session.is_active = False
                session.updated_at = datetime.utcnow()
                
                logger.info(
                    f"[session_manager] Logged out session: "
                    f"session_id={session.session_id}, platform={session.platform}"
                )
                
                # Invalidate cache
                self.cache.invalidate_user(session.user_type, session.user_id)
                self.cache.invalidate_session(session.session_id)
            
            self.db.commit()
            
            logger.info(
                f"[session_manager] Logout successful: "
                f"{user_type}:{user_id}, sessions={len(sessions)}"
            )
            
            return True
            
        except Exception as e:
            logger.error(
                f"[session_manager] Error during logout: {e}",
                exc_info=True
            )
            self.db.rollback()
            return False
    
    def cleanup_expired_sessions(self) -> int:
        """
        Cleanup expired sessions (background job)
        
        Deactivates sessions where:
        - expires_at < now()
        - is_active = True
        
        Returns:
            Number of sessions deactivated
        """
        try:
            now = datetime.utcnow()
            
            # Find expired sessions
            expired_sessions = self.db.query(UserSession).filter(
                UserSession.is_active == True,
                UserSession.expires_at < now
            ).all()
            
            if not expired_sessions:
                logger.debug("[session_manager] No expired sessions to cleanup")
                return 0
            
            # Deactivate and invalidate cache
            for session in expired_sessions:
                session.is_active = False
                session.updated_at = now
                
                self.cache.invalidate_user(session.user_type, session.user_id)
                self.cache.invalidate_session(session.session_id)
            
            self.db.commit()
            
            count = len(expired_sessions)
            logger.info(f"[session_manager] Cleaned up {count} expired sessions")
            
            return count
            
        except Exception as e:
            logger.error(
                f"[session_manager] Error during cleanup: {e}",
                exc_info=True
            )
            self.db.rollback()
            return 0
    
    def get_user_sessions_info(
        self,
        user_type: str,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Get session information for user (all sessions, active and inactive)
        
        Args:
            user_type: User type
            user_id: User ID
            
        Returns:
            Dict with session information
        """
        try:
            sessions = self.db.query(UserSession).filter_by(
                user_type=user_type,
                user_id=user_id
            ).order_by(UserSession.created_at.desc()).all()
            
            active_sessions = [s for s in sessions if s.is_active]
            inactive_sessions = [s for s in sessions if not s.is_active]
            
            result = {
                "user_type": user_type,
                "user_id": user_id,
                "total_sessions": len(sessions),
                "active_sessions": len(active_sessions),
                "inactive_sessions": len(inactive_sessions),
                "active_platforms": [s.platform for s in active_sessions],
                "sessions": [s.to_dict() for s in sessions[:10]]  # Last 10 sessions
            }
            
            logger.debug(
                f"[session_manager] Session info: {user_type}:{user_id}, "
                f"active={len(active_sessions)}, total={len(sessions)}"
            )
            
            return result
            
        except Exception as e:
            logger.error(
                f"[session_manager] Error getting session info: {e}",
                exc_info=True
            )
            return {
                "error": str(e),
                "user_type": user_type,
                "user_id": user_id
            }


# Import sqlalchemy here to avoid circular import
import sqlalchemy as sa

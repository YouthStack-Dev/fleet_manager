"""
Comprehensive Test Suite for Push Notification Registration System

Tests the core business logic:
1. Single active session per user per platform
2. Multiple inactive sessions for history
3. Token reuse handling
4. Session lifecycle (register, logout, expire)
5. Concurrent platform support (web + app)
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.user_session import UserSession
from app.services.session_manager import SessionManager
from app.services.session_cache import SessionCache
from unittest.mock import MagicMock


@pytest.fixture
def db_session(test_db: Session):
    """Provide a clean database session for each test"""
    yield test_db
    # Cleanup after each test
    test_db.query(UserSession).delete()
    test_db.commit()


@pytest.fixture
def mock_cache():
    """Mock Redis cache to avoid external dependencies"""
    cache = MagicMock(spec=SessionCache)
    cache.set_token = MagicMock()
    cache.set_platform = MagicMock()
    cache.set_session = MagicMock()
    cache.invalidate_user = MagicMock()
    cache.invalidate_session = MagicMock()
    return cache


@pytest.fixture
def session_manager(db_session: Session, mock_cache):
    """Create SessionManager with mocked cache"""
    return SessionManager(db_session, mock_cache)


class TestTokenRegistrationBasics:
    """Test basic token registration functionality"""
    
    def test_register_new_token_success(self, session_manager: SessionManager, db_session: Session):
        """Test: First-time token registration succeeds"""
        session = session_manager.register_session(
            user_type="employee",
            user_id=1,
            tenant_id="TEST001",
            platform="app",
            fcm_token="a" * 152,  # Valid FCM token
            device_info={"device_type": "android", "app_version": "1.0.0"}
        )
        
        assert session is not None
        assert session.user_type == "employee"
        assert session.user_id == 1
        assert session.platform == "app"
        assert session.is_active is True
        assert session.fcm_token == "a" * 152
        
        # Verify in database
        db_sessions = db_session.query(UserSession).filter_by(user_id=1).all()
        assert len(db_sessions) == 1
        assert db_sessions[0].is_active is True
    
    def test_register_token_with_minimal_info(self, session_manager: SessionManager):
        """Test: Registration works with minimal required fields"""
        session = session_manager.register_session(
            user_type="employee",
            user_id=2,
            tenant_id="TEST001",
            platform="web",
            fcm_token="b" * 152
        )
        
        assert session is not None
        assert session.device_type is None
        assert session.app_version is None
    
    def test_register_invalid_user_type(self, session_manager: SessionManager):
        """Test: Invalid user_type raises ValueError"""
        with pytest.raises(ValueError, match="Invalid user_type"):
            session_manager.register_session(
                user_type="invalid_type",
                user_id=1,
                tenant_id="TEST001",
                platform="app",
                fcm_token="c" * 152
            )
    
    def test_register_invalid_platform(self, session_manager: SessionManager):
        """Test: Invalid platform raises ValueError"""
        with pytest.raises(ValueError, match="Invalid platform"):
            session_manager.register_session(
                user_type="employee",
                user_id=1,
                tenant_id="TEST001",
                platform="desktop",  # Invalid
                fcm_token="d" * 152
            )
    
    def test_register_invalid_fcm_token(self, session_manager: SessionManager):
        """Test: Too short FCM token raises ValueError"""
        with pytest.raises(ValueError, match="Invalid FCM token format"):
            session_manager.register_session(
                user_type="employee",
                user_id=1,
                tenant_id="TEST001",
                platform="app",
                fcm_token="short"  # Too short
            )


class TestSingleActiveSessionConstraint:
    """Test that only one active session per user per platform is allowed"""
    
    def test_reregister_same_platform_deactivates_old(
        self, session_manager: SessionManager, db_session: Session
    ):
        """Test: Re-registering on same platform deactivates old session"""
        # First registration
        session1 = session_manager.register_session(
            user_type="employee",
            user_id=1,
            tenant_id="TEST001",
            platform="app",
            fcm_token="first_token" + "x" * 140
        )
        
        # Second registration on same platform
        session2 = session_manager.register_session(
            user_type="employee",
            user_id=1,
            tenant_id="TEST001",
            platform="app",
            fcm_token="second_token" + "x" * 139
        )
        
        # Verify old session is deactivated
        db_session.refresh(session1)
        assert session1.is_active is False
        assert session1.fcm_token is None  # Token cleared
        
        # Verify new session is active
        assert session2.is_active is True
        assert session2.fcm_token == "second_token" + "x" * 139
        
        # Verify only ONE active session exists
        active_sessions = db_session.query(UserSession).filter_by(
            user_id=1, platform="app", is_active=True
        ).all()
        assert len(active_sessions) == 1
        assert active_sessions[0].session_id == session2.session_id
    
    def test_reregister_same_token_allowed(
        self, session_manager: SessionManager, db_session: Session
    ):
        """Test: Re-registering with same FCM token is allowed (no unique constraint on token)"""
        token = "same_token" + "x" * 142
        
        # First registration
        session1 = session_manager.register_session(
            user_type="employee",
            user_id=1,
            tenant_id="TEST001",
            platform="app",
            fcm_token=token
        )
        
        # Second registration with SAME token
        session2 = session_manager.register_session(
            user_type="employee",
            user_id=1,
            tenant_id="TEST001",
            platform="app",
            fcm_token=token
        )
        
        # Should succeed - old session cleared, new session created
        db_session.refresh(session1)
        assert session1.fcm_token is None  # Cleared
        assert session2.fcm_token == token  # Active
        
        # Both sessions exist in DB (one inactive, one active)
        all_sessions = db_session.query(UserSession).filter_by(user_id=1).all()
        assert len(all_sessions) == 2
    
    def test_multiple_inactive_sessions_allowed(
        self, session_manager: SessionManager, db_session: Session
    ):
        """Test: Multiple inactive sessions for same user/platform are allowed"""
        # Register 5 times on same platform
        for i in range(5):
            session_manager.register_session(
                user_type="employee",
                user_id=1,
                tenant_id="TEST001",
                platform="app",
                fcm_token=f"token_{i}" + "x" * 145
            )
        
        # Verify 5 sessions exist
        all_sessions = db_session.query(UserSession).filter_by(
            user_type="employee", user_id=1, platform="app"
        ).all()
        assert len(all_sessions) == 5
        
        # Verify only 1 is active
        active_sessions = [s for s in all_sessions if s.is_active]
        assert len(active_sessions) == 1
        
        # Verify 4 are inactive with cleared tokens
        inactive_sessions = [s for s in all_sessions if not s.is_active]
        assert len(inactive_sessions) == 4
        for session in inactive_sessions:
            assert session.fcm_token is None


class TestMultiplePlatformSupport:
    """Test that users can be active on both web and app simultaneously"""
    
    def test_register_both_platforms_simultaneously(
        self, session_manager: SessionManager, db_session: Session
    ):
        """Test: User can have active sessions on both web and app"""
        # Register on app
        app_session = session_manager.register_session(
            user_type="employee",
            user_id=1,
            tenant_id="TEST001",
            platform="app",
            fcm_token="app_token" + "x" * 143
        )
        
        # Register on web
        web_session = session_manager.register_session(
            user_type="employee",
            user_id=1,
            tenant_id="TEST001",
            platform="web",
            fcm_token="web_token" + "x" * 143
        )
        
        # Both should be active
        assert app_session.is_active is True
        assert web_session.is_active is True
        
        # Verify in database
        active_sessions = db_session.query(UserSession).filter_by(
            user_id=1, is_active=True
        ).all()
        assert len(active_sessions) == 2
        
        platforms = {s.platform for s in active_sessions}
        assert platforms == {"app", "web"}
    
    def test_logout_one_platform_keeps_other_active(
        self, session_manager: SessionManager, db_session: Session
    ):
        """Test: Logging out from one platform doesn't affect the other"""
        # Register on both platforms
        session_manager.register_session(
            user_type="employee", user_id=1, tenant_id="TEST001",
            platform="app", fcm_token="app" + "x" * 149
        )
        session_manager.register_session(
            user_type="employee", user_id=1, tenant_id="TEST001",
            platform="web", fcm_token="web" + "x" * 149
        )
        
        # Logout from app only
        session_manager.logout_session(
            user_type="employee",
            user_id=1,
            platform="app"
        )
        
        # Verify app is inactive, web is still active
        active_sessions = db_session.query(UserSession).filter_by(
            user_id=1, is_active=True
        ).all()
        assert len(active_sessions) == 1
        assert active_sessions[0].platform == "web"


class TestSessionLifecycle:
    """Test session lifecycle: register, logout, expire"""
    
    def test_logout_deactivates_and_clears_token(
        self, session_manager: SessionManager, db_session: Session
    ):
        """Test: Logout sets is_active=False and clears fcm_token"""
        session = session_manager.register_session(
            user_type="employee", user_id=1, tenant_id="TEST001",
            platform="app", fcm_token="logout_test" + "x" * 141
        )
        
        # Logout
        success = session_manager.logout_session(
            user_type="employee", user_id=1, platform="app"
        )
        
        assert success is True
        
        # Verify session is deactivated and token cleared
        db_session.refresh(session)
        assert session.is_active is False
        assert session.fcm_token is None
    
    def test_logout_all_platforms(
        self, session_manager: SessionManager, db_session: Session
    ):
        """Test: Logout without platform parameter deactivates all platforms"""
        # Register on both platforms
        session_manager.register_session(
            user_type="employee", user_id=1, tenant_id="TEST001",
            platform="app", fcm_token="a" * 152
        )
        session_manager.register_session(
            user_type="employee", user_id=1, tenant_id="TEST001",
            platform="web", fcm_token="b" * 152
        )
        
        # Logout from all platforms
        session_manager.logout_session(
            user_type="employee", user_id=1, platform=None
        )
        
        # Verify both are deactivated
        active_sessions = db_session.query(UserSession).filter_by(
            user_id=1, is_active=True
        ).all()
        assert len(active_sessions) == 0
    
    def test_cleanup_expired_sessions(
        self, session_manager: SessionManager, db_session: Session
    ):
        """Test: Expired sessions are cleaned up and tokens cleared"""
        # Create a session with past expiry
        expired_session = UserSession(
            user_type="employee",
            user_id=1,
            tenant_id="TEST001",
            platform="app",
            fcm_token="expired" + "x" * 145,
            is_active=True,
            last_activity_at=datetime.utcnow(),
            expires_at=datetime.utcnow() - timedelta(days=1)  # Expired
        )
        db_session.add(expired_session)
        db_session.commit()
        
        # Run cleanup
        count = session_manager.cleanup_expired_sessions()
        
        assert count == 1
        
        # Verify session is deactivated and token cleared
        db_session.refresh(expired_session)
        assert expired_session.is_active is False
        assert expired_session.fcm_token is None


class TestMultiUserScenarios:
    """Test scenarios with multiple users"""
    
    def test_different_users_same_platform(
        self, session_manager: SessionManager, db_session: Session
    ):
        """Test: Different users can have active sessions on same platform"""
        # User 1
        session_manager.register_session(
            user_type="employee", user_id=1, tenant_id="TEST001",
            platform="app", fcm_token="user1" + "x" * 147
        )
        
        # User 2
        session_manager.register_session(
            user_type="employee", user_id=2, tenant_id="TEST001",
            platform="app", fcm_token="user2" + "x" * 147
        )
        
        # Both should be active
        active_sessions = db_session.query(UserSession).filter_by(
            platform="app", is_active=True
        ).all()
        assert len(active_sessions) == 2
    
    def test_different_user_types_independent(
        self, session_manager: SessionManager, db_session: Session
    ):
        """Test: Different user types (employee, driver, etc.) are independent"""
        # Employee with user_id=1
        session_manager.register_session(
            user_type="employee", user_id=1, tenant_id="TEST001",
            platform="app", fcm_token="employee" + "x" * 144
        )
        
        # Driver with user_id=1 (different user_type)
        session_manager.register_session(
            user_type="driver", user_id=1, tenant_id="TEST001",
            platform="app", fcm_token="driver" + "x" * 146
        )
        
        # Both should be active (different user_type)
        active_sessions = db_session.query(UserSession).filter_by(
            user_id=1, is_active=True
        ).all()
        assert len(active_sessions) == 2
        
        user_types = {s.user_type for s in active_sessions}
        assert user_types == {"employee", "driver"}


class TestGetActiveSession:
    """Test retrieving active sessions"""
    
    def test_get_active_session_exists(
        self, session_manager: SessionManager, db_session: Session
    ):
        """Test: Get active session returns correct session"""
        created_session = session_manager.register_session(
            user_type="employee", user_id=1, tenant_id="TEST001",
            platform="app", fcm_token="a" * 152
        )
        
        retrieved_session = session_manager.get_active_session(
            user_type="employee", user_id=1, platform="app"
        )
        
        assert retrieved_session is not None
        assert retrieved_session.session_id == created_session.session_id
    
    def test_get_active_session_not_exists(
        self, session_manager: SessionManager
    ):
        """Test: Get active session returns None when no session exists"""
        session = session_manager.get_active_session(
            user_type="employee", user_id=999, platform="app"
        )
        
        assert session is None
    
    def test_get_active_session_ignores_inactive(
        self, session_manager: SessionManager, db_session: Session
    ):
        """Test: Get active session ignores inactive sessions"""
        # Create inactive session
        inactive_session = UserSession(
            user_type="employee", user_id=1, tenant_id="TEST001",
            platform="app", fcm_token=None, is_active=False,
            last_activity_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
        db_session.add(inactive_session)
        db_session.commit()
        
        # Try to get active session
        session = session_manager.get_active_session(
            user_type="employee", user_id=1, platform="app"
        )
        
        assert session is None


class TestBatchOperations:
    """Test batch operations for performance"""
    
    def test_get_active_sessions_batch(
        self, session_manager: SessionManager, db_session: Session
    ):
        """Test: Batch retrieval of active sessions"""
        # Create sessions for multiple users
        for user_id in range(1, 4):
            session_manager.register_session(
                user_type="employee",
                user_id=user_id,
                tenant_id="TEST001",
                platform="app",
                fcm_token=f"user{user_id}" + "x" * 147
            )
        
        # Batch retrieve
        recipients = [
            {"user_type": "employee", "user_id": 1},
            {"user_type": "employee", "user_id": 2},
            {"user_type": "employee", "user_id": 3},
            {"user_type": "employee", "user_id": 999},  # Doesn't exist
        ]
        
        sessions = session_manager.get_active_sessions_batch(recipients)
        
        assert len(sessions) == 3  # Only 3 exist
        user_ids = {s.user_id for s in sessions}
        assert user_ids == {1, 2, 3}


class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_session_expiry_default_30_days(
        self, session_manager: SessionManager, db_session: Session
    ):
        """Test: Sessions default to 30-day expiry"""
        session = session_manager.register_session(
            user_type="employee", user_id=1, tenant_id="TEST001",
            platform="app", fcm_token="a" * 152
        )
        
        # Check expiry is approximately 30 days from now
        expected_expiry = datetime.utcnow() + timedelta(days=30)
        time_diff = abs((session.expires_at - expected_expiry).total_seconds())
        assert time_diff < 10  # Within 10 seconds
    
    def test_register_updates_last_activity(
        self, session_manager: SessionManager, db_session: Session
    ):
        """Test: Registration updates last_activity_at"""
        session = session_manager.register_session(
            user_type="employee", user_id=1, tenant_id="TEST001",
            platform="app", fcm_token="a" * 152
        )
        
        time_diff = abs((session.last_activity_at - datetime.utcnow()).total_seconds())
        assert time_diff < 5  # Within 5 seconds
    
    def test_get_user_sessions_info(
        self, session_manager: SessionManager, db_session: Session
    ):
        """Test: Get comprehensive user session information"""
        # Create mix of active and inactive sessions
        session_manager.register_session(
            user_type="employee", user_id=1, tenant_id="TEST001",
            platform="app", fcm_token="token1" + "x" * 146
        )
        session_manager.register_session(
            user_type="employee", user_id=1, tenant_id="TEST001",
            platform="app", fcm_token="token2" + "x" * 146
        )
        session_manager.register_session(
            user_type="employee", user_id=1, tenant_id="TEST001",
            platform="web", fcm_token="token3" + "x" * 146
        )
        
        info = session_manager.get_user_sessions_info(
            user_type="employee", user_id=1
        )
        
        assert info["total_sessions"] == 3
        assert info["active_sessions"] == 2
        assert info["inactive_sessions"] == 1
        assert set(info["active_platforms"]) == {"app", "web"}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

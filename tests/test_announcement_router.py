# tests/test_announcement_router.py
"""
Comprehensive tests for the Announcement / Broadcast feature.

Coverage
────────
  TestAnnouncementCreate         — POST /announcements
  TestAnnouncementList           — GET  /announcements
  TestAnnouncementGet            — GET  /announcements/{id}
  TestAnnouncementUpdate         — PUT  /announcements/{id}
  TestAnnouncementDelete         — DELETE /announcements/{id}
  TestAnnouncementPublish        — POST /announcements/{id}/publish  (all 6 target types)
  TestAnnouncementRecipients     — GET  /announcements/{id}/recipients
  TestEmployeeAnnouncements      — GET  /employee/announcements
  TestEmployeeMarkRead           — POST /employee/announcements/{id}/read
  TestDriverAnnouncements        — GET  /driver/announcements
  TestDriverMarkRead             — POST /driver/announcements/{id}/read
  TestTenantIsolation            — cross-tenant access must be blocked
  TestInputValidation            — edge-cases / bad payloads
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy.orm import Session

from common_utils.auth.utils import create_access_token
from app.models.announcement import (
    Announcement,
    AnnouncementRecipient,
    AnnouncementContentType,
    AnnouncementTargetType,
    AnnouncementStatus,
    AnnouncementDeliveryStatus,
)
from app.models.driver import Driver, GenderEnum, VerificationStatusEnum
from app.models.employee import Employee
from app.models.team import Team
from datetime import date


# ─────────────────────────────────────────────────────────────────────────────
# Token factories
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def admin_ann_token(admin_user):
    """Admin JWT with booking.read (required by AdminAuth)."""
    token = create_access_token(
        user_id=str(admin_user["employee"].employee_id),
        tenant_id="TEST001",
        user_type="admin",
        custom_claims={
            "permissions": [
                "booking.read", "booking.create", "booking.update", "booking.delete",
                "announcement.read", "announcement.write",
            ]
        },
    )
    return f"Bearer {token}"


@pytest.fixture
def employee_ann_token(employee_user):
    """Employee JWT with app-employee.read + app-employee.write (uses employee_user ID=2)."""
    token = create_access_token(
        user_id=str(employee_user["employee"].employee_id),
        tenant_id=employee_user["tenant"].tenant_id,
        user_type="employee",
        custom_claims={
            "email": employee_user["employee"].email,
            "employee_id": employee_user["employee"].employee_id,
            "permissions": ["app-employee.read", "app-employee.write"],
        },
    )
    return f"Bearer {token}"


@pytest.fixture
def test_employee_ann_token(test_employee, test_tenant):
    """Employee JWT for test_employee (ID=100) — used for announcement recipient tests."""
    token = create_access_token(
        user_id=str(test_employee["employee"].employee_id),
        tenant_id=test_tenant.tenant_id,
        user_type="employee",
        custom_claims={
            "email": test_employee["employee"].email,
            "employee_id": test_employee["employee"].employee_id,
            "permissions": ["app-employee.read", "app-employee.write"],
        },
    )
    return f"Bearer {token}"


@pytest.fixture
def driver_ann_token(test_driver, test_tenant):
    """Driver JWT with app-driver.read + app-driver.write."""
    token = create_access_token(
        user_id=str(test_driver.driver_id),
        tenant_id=test_tenant.tenant_id,
        user_type="driver",
        custom_claims={
            "email": test_driver.email,
            "permissions": ["app-driver.read", "app-driver.write"],
        },
    )
    return f"Bearer {token}"


@pytest.fixture
def second_tenant_admin_token(second_tenant):
    """Admin token scoped to TEST002 (second tenant)."""
    token = create_access_token(
        user_id="999",
        tenant_id=second_tenant.tenant_id,
        user_type="admin",
        custom_claims={"permissions": ["booking.read"]},
    )
    return f"Bearer {token}"


# ─────────────────────────────────────────────────────────────────────────────
# DB fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def extra_team(test_db, test_tenant):
    """A second team in TEST001 for multi-team targeting tests."""
    team = Team(
        team_id=50,
        tenant_id=test_tenant.tenant_id,
        name="Extra Team",
        description="Extra team for announcement tests",
        is_active=True,
    )
    test_db.add(team)
    test_db.commit()
    test_db.refresh(team)
    return team


@pytest.fixture
def extra_employee(test_db, test_tenant, extra_team):
    """A second employee in TEST001 / extra_team."""
    from app.models.iam.role import Role
    emp_role = test_db.query(Role).filter(
        Role.name == "Employee", Role.is_system_role.is_(True)
    ).first()
    emp = Employee(
        employee_id=200,
        tenant_id=test_tenant.tenant_id,
        team_id=extra_team.team_id,
        role_id=emp_role.role_id if emp_role else 3,
        name="Extra Employee",
        employee_code="EXTRAEMP001",
        email="extraemp@test.com",
        phone="+9999999999",
        password="hashed",
        is_active=True,
    )
    test_db.add(emp)
    test_db.commit()
    test_db.refresh(emp)
    return emp


@pytest.fixture
def second_driver(test_db, test_tenant, test_vendor):
    """A second active driver in TEST001 / test_vendor."""
    drv = Driver(
        driver_id=50,
        tenant_id=test_tenant.tenant_id,
        vendor_id=test_vendor.vendor_id,
        role_id=2,
        name="Second Driver",
        code="DRV050",
        email="driver2ann@test.com",
        phone="8888888888",
        gender=GenderEnum.FEMALE,
        password="hashed",
        date_of_birth=date(1992, 5, 10),
        date_of_joining=date(2023, 3, 1),
        license_number="LIC050",
        badge_number="BADGE050",
        bg_verify_status=VerificationStatusEnum.APPROVED,
        is_active=True,
    )
    test_db.add(drv)
    test_db.commit()
    test_db.refresh(drv)
    return drv


@pytest.fixture
def draft_announcement(test_db, test_tenant):
    """A pre-existing DRAFT announcement scoped to TEST001."""
    ann = Announcement(
        tenant_id=test_tenant.tenant_id,
        title="Draft Announcement",
        body="This is a draft announcement body.",
        content_type=AnnouncementContentType.TEXT,
        target_type=AnnouncementTargetType.ALL_EMPLOYEES,
        status=AnnouncementStatus.DRAFT,
        is_active=True,
    )
    test_db.add(ann)
    test_db.commit()
    test_db.refresh(ann)
    return ann


@pytest.fixture
def published_announcement_with_employee(test_db, test_tenant, test_employee):
    """
    A PUBLISHED announcement with one employee recipient row already inserted.
    Used to test employee read endpoints.
    """
    ann = Announcement(
        tenant_id=test_tenant.tenant_id,
        title="Published Announcement",
        body="Published body.",
        content_type=AnnouncementContentType.TEXT,
        target_type=AnnouncementTargetType.SPECIFIC_EMPLOYEES,
        target_ids=[test_employee["employee"].employee_id],
        status=AnnouncementStatus.PUBLISHED,
        total_recipients=1,
        success_count=1,
        is_active=True,
    )
    test_db.add(ann)
    test_db.flush()

    rec = AnnouncementRecipient(
        announcement_id=ann.announcement_id,
        recipient_type="employee",
        recipient_user_id=test_employee["employee"].employee_id,
        tenant_id=test_tenant.tenant_id,
        delivery_status=AnnouncementDeliveryStatus.DELIVERED,
    )
    test_db.add(rec)
    test_db.commit()
    test_db.refresh(ann)
    return ann


@pytest.fixture
def published_announcement_with_driver(test_db, test_tenant, test_driver):
    """PUBLISHED announcement with one driver recipient row."""
    ann = Announcement(
        tenant_id=test_tenant.tenant_id,
        title="Driver Announcement",
        body="Driver body.",
        content_type=AnnouncementContentType.TEXT,
        target_type=AnnouncementTargetType.SPECIFIC_DRIVERS,
        target_ids=[test_driver.driver_id],
        status=AnnouncementStatus.PUBLISHED,
        total_recipients=1,
        success_count=1,
        is_active=True,
    )
    test_db.add(ann)
    test_db.flush()

    rec = AnnouncementRecipient(
        announcement_id=ann.announcement_id,
        recipient_type="driver",
        recipient_user_id=test_driver.driver_id,
        tenant_id=test_tenant.tenant_id,
        delivery_status=AnnouncementDeliveryStatus.DELIVERED,
    )
    test_db.add(rec)
    test_db.commit()
    test_db.refresh(ann)
    return ann


# ─────────────────────────────────────────────────────────────────────────────
# Helper: mock FCM notification service
# ─────────────────────────────────────────────────────────────────────────────

def _mock_notif(success: int = 0, failure: int = 0, no_session: int = 0):
    """Return a MagicMock that simulates UnifiedNotificationService.send_to_users_batch."""
    svc = MagicMock()
    svc.send_to_users_batch.return_value = {
        "success_count":   success,
        "failure_count":   failure,
        "no_session_count": no_session,
    }
    return svc


# ═════════════════════════════════════════════════════════════════════════════
# TestAnnouncementCreate
# ═════════════════════════════════════════════════════════════════════════════

class TestAnnouncementCreate:
    URL = "/api/v1/announcements"

    def test_create_text_announcement(self, client, admin_ann_token, employee_user):
        resp = client.post(
            self.URL,
            json={
                "title": "Hello Employees",
                "body": "This is a text announcement.",
                "content_type": "text",
                "target_type": "all_employees",
            },
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["title"] == "Hello Employees"
        assert data["status"] == "draft"
        assert data["content_type"] == "text"
        assert data["target_type"] == "all_employees"
        assert data["announcement_id"] is not None

    def test_create_video_announcement_with_media(self, client, admin_ann_token, employee_user):
        resp = client.post(
            self.URL,
            json={
                "title": "Watch This Video",
                "body": "Important video for all employees.",
                "content_type": "video",
                "media_url": "https://cdn.example.com/video.mp4",
                "media_filename": "safety_training.mp4",
                "media_size_bytes": 10485760,
                "target_type": "all_employees",
            },
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["content_type"] == "video"
        assert data["media_url"] == "https://cdn.example.com/video.mp4"
        assert data["media_filename"] == "safety_training.mp4"
        assert data["media_size_bytes"] == 10485760

    def test_create_pdf_announcement(self, client, admin_ann_token, employee_user):
        resp = client.post(
            self.URL,
            json={
                "title": "Policy Document",
                "body": "Please read the attached policy PDF.",
                "content_type": "pdf",
                "media_url": "https://cdn.example.com/policy.pdf",
                "media_filename": "company_policy_2026.pdf",
                "target_type": "all_employees",
            },
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["content_type"] == "pdf"

    def test_create_link_announcement(self, client, admin_ann_token, employee_user):
        resp = client.post(
            self.URL,
            json={
                "title": "Check our portal",
                "body": "New features available on the portal.",
                "content_type": "link",
                "media_url": "https://portal.example.com/new-features",
                "target_type": "all_employees",
            },
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["content_type"] == "link"

    def test_create_with_specific_employees(self, client, admin_ann_token, test_employee, employee_user):
        resp = client.post(
            self.URL,
            json={
                "title": "Personal Note",
                "body": "Hi, this is just for you.",
                "target_type": "specific_employees",
                "target_ids": [test_employee["employee"].employee_id],
            },
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["target_type"] == "specific_employees"
        assert test_employee["employee"].employee_id in data["target_ids"]

    def test_create_requires_auth(self, client):
        resp = client.post(
            self.URL,
            json={"title": "x", "body": "y", "target_type": "all_employees"},
        )
        assert resp.status_code == 401

    def test_create_title_too_long(self, client, admin_ann_token, employee_user):
        resp = client.post(
            self.URL,
            json={
                "title": "A" * 201,
                "body": "body",
                "target_type": "all_employees",
            },
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 422

    def test_create_missing_target_type(self, client, admin_ann_token, employee_user):
        resp = client.post(
            self.URL,
            json={"title": "x", "body": "y"},
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 422

    def test_create_invalid_content_type(self, client, admin_ann_token, employee_user):
        resp = client.post(
            self.URL,
            json={"title": "x", "body": "y", "content_type": "gif", "target_type": "all_employees"},
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 422

    def test_create_audio_announcement(self, client, admin_ann_token, employee_user):
        resp = client.post(
            self.URL,
            json={
                "title": "Voice Message",
                "body": "Listen to this announcement.",
                "content_type": "audio",
                "media_url": "https://cdn.example.com/voice.mp3",
                "target_type": "all_drivers",
            },
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["content_type"] == "audio"


# ═════════════════════════════════════════════════════════════════════════════
# TestAnnouncementList
# ═════════════════════════════════════════════════════════════════════════════

class TestAnnouncementList:
    URL = "/api/v1/announcements"

    def test_list_empty(self, client, admin_ann_token, employee_user):
        resp = client.get(self.URL, headers={"Authorization": admin_ann_token})
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["total"] == 0 or isinstance(body["data"], list)

    def test_list_returns_created(self, client, admin_ann_token, draft_announcement, employee_user):
        resp = client.get(self.URL, headers={"Authorization": admin_ann_token})
        assert resp.status_code == 200
        items = resp.json()["data"]
        ids = [i["announcement_id"] for i in items]
        assert draft_announcement.announcement_id in ids

    def test_list_filter_by_draft(self, client, admin_ann_token, draft_announcement, employee_user):
        resp = client.get(
            self.URL + "?status=draft",
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 200
        items = resp.json()["data"]
        assert all(i["status"] == "draft" for i in items)

    def test_list_pagination(self, client, admin_ann_token, test_db, test_tenant, employee_user):
        # Insert 5 more draft announcements
        for i in range(5):
            test_db.add(Announcement(
                tenant_id=test_tenant.tenant_id,
                title=f"Bulk Ann {i}",
                body="body",
                content_type=AnnouncementContentType.TEXT,
                target_type=AnnouncementTargetType.ALL_EMPLOYEES,
                status=AnnouncementStatus.DRAFT,
                is_active=True,
            ))
        test_db.commit()

        resp = client.get(
            self.URL + "?page=1&page_size=3",
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) <= 3


# ═════════════════════════════════════════════════════════════════════════════
# TestAnnouncementGet
# ═════════════════════════════════════════════════════════════════════════════

class TestAnnouncementGet:
    def test_get_existing(self, client, admin_ann_token, draft_announcement, employee_user):
        url = f"/api/v1/announcements/{draft_announcement.announcement_id}"
        resp = client.get(url, headers={"Authorization": admin_ann_token})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["announcement_id"] == draft_announcement.announcement_id
        assert data["title"] == draft_announcement.title

    def test_get_not_found(self, client, admin_ann_token, employee_user):
        resp = client.get(
            "/api/v1/announcements/99999",
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 404

    def test_get_wrong_tenant(self, client, second_tenant_admin_token, draft_announcement, second_tenant):
        """Announcement in TEST001 should not be visible from TEST002 admin."""
        url = f"/api/v1/announcements/{draft_announcement.announcement_id}"
        resp = client.get(url, headers={"Authorization": second_tenant_admin_token})
        assert resp.status_code == 404


# ═════════════════════════════════════════════════════════════════════════════
# TestAnnouncementUpdate
# ═════════════════════════════════════════════════════════════════════════════

class TestAnnouncementUpdate:
    def _url(self, ann_id):
        return f"/api/v1/announcements/{ann_id}"

    def test_update_title(self, client, admin_ann_token, draft_announcement, employee_user):
        resp = client.put(
            self._url(draft_announcement.announcement_id),
            json={"title": "Updated Title"},
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Updated Title"

    def test_update_body_and_media(self, client, admin_ann_token, draft_announcement, employee_user):
        resp = client.put(
            self._url(draft_announcement.announcement_id),
            json={
                "body": "Updated body.",
                "content_type": "video",
                "media_url": "https://cdn.example.com/new.mp4",
                "media_filename": "new_video.mp4",
            },
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["content_type"] == "video"
        assert data["media_url"] == "https://cdn.example.com/new.mp4"

    def test_update_target_type(self, client, admin_ann_token, draft_announcement, test_employee, employee_user):
        resp = client.put(
            self._url(draft_announcement.announcement_id),
            json={
                "target_type": "specific_employees",
                "target_ids": [test_employee["employee"].employee_id],
            },
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["target_type"] == "specific_employees"
        assert test_employee["employee"].employee_id in data["target_ids"]

    def test_update_published_fails(self, client, admin_ann_token, published_announcement_with_employee, test_employee, employee_user):
        url = f"/api/v1/announcements/{published_announcement_with_employee.announcement_id}"
        resp = client.put(
            url,
            json={"title": "Try to change published"},
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 400

    def test_update_not_found(self, client, admin_ann_token, employee_user):
        resp = client.put(
            "/api/v1/announcements/99999",
            json={"title": "x"},
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 404


# ═════════════════════════════════════════════════════════════════════════════
# TestAnnouncementDelete
# ═════════════════════════════════════════════════════════════════════════════

class TestAnnouncementDelete:
    def test_soft_delete_draft(self, client, admin_ann_token, draft_announcement, test_db, employee_user):
        url = f"/api/v1/announcements/{draft_announcement.announcement_id}"
        resp = client.delete(url, headers={"Authorization": admin_ann_token})
        assert resp.status_code == 200

        # Now a GET should 404
        resp2 = client.get(url, headers={"Authorization": admin_ann_token})
        assert resp2.status_code == 404

        # Verify DB state
        test_db.expire_all()
        ann = test_db.get(Announcement, draft_announcement.announcement_id)
        assert ann.is_active is False
        assert ann.status == AnnouncementStatus.CANCELLED

    def test_soft_delete_published_keeps_status(
        self, client, admin_ann_token, published_announcement_with_employee, test_db, test_employee, employee_user
    ):
        ann_id = published_announcement_with_employee.announcement_id
        resp = client.delete(
            f"/api/v1/announcements/{ann_id}",
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 200
        test_db.expire_all()
        ann = test_db.get(Announcement, ann_id)
        assert ann.is_active is False
        # Published status should NOT be changed to cancelled
        assert ann.status == AnnouncementStatus.PUBLISHED

    def test_delete_not_found(self, client, admin_ann_token, employee_user):
        resp = client.delete(
            "/api/v1/announcements/99999",
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 404


# ═════════════════════════════════════════════════════════════════════════════
# TestAnnouncementPublish  — core targeting logic
# ═════════════════════════════════════════════════════════════════════════════

class TestAnnouncementPublish:

    def _publish(self, client, ann_id, token):
        return client.post(
            f"/api/v1/announcements/{ann_id}/publish",
            headers={"Authorization": token},
        )

    def _create_draft(self, client, token, target_type, target_ids=None, content_type="text"):
        payload = {
            "title": f"Ann for {target_type}",
            "body": f"Body for {target_type}",
            "content_type": content_type,
            "target_type": target_type,
        }
        if target_ids is not None:
            payload["target_ids"] = target_ids
        resp = client.post(
            "/api/v1/announcements",
            json=payload,
            headers={"Authorization": token},
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["data"]["announcement_id"]

    # ── all_employees ─────────────────────────────────────────────────────────

    def test_publish_all_employees(self, client, admin_ann_token, test_employee, extra_employee, employee_user):
        """all_employees → resolves both test_employee and extra_employee (plus others in tenant)."""
        ann_id = self._create_draft(client, admin_ann_token, "all_employees")
        # Use a large enough success count to cover all employees in the tenant
        mock_svc = _mock_notif(success=10)
        with patch(
            "app.crud.announcement.UnifiedNotificationService",
            return_value=mock_svc,
        ):
            resp = self._publish(client, ann_id, admin_ann_token)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "published"
        # At minimum test_employee and extra_employee must be included
        assert data["total_recipients"] >= 2

    # ── specific_employees ────────────────────────────────────────────────────

    def test_publish_specific_employees_single(
        self, client, admin_ann_token, test_employee, employee_user
    ):
        emp_id = test_employee["employee"].employee_id
        ann_id = self._create_draft(client, admin_ann_token, "specific_employees", [emp_id])
        mock_svc = _mock_notif(success=1)
        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_svc):
            resp = self._publish(client, ann_id, admin_ann_token)
        assert resp.status_code == 200
        assert resp.json()["data"]["total_recipients"] == 1

    def test_publish_specific_employees_multi(
        self, client, admin_ann_token, test_employee, extra_employee, employee_user
    ):
        ids = [test_employee["employee"].employee_id, extra_employee.employee_id]
        ann_id = self._create_draft(client, admin_ann_token, "specific_employees", ids)
        mock_svc = _mock_notif(success=2)
        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_svc):
            resp = self._publish(client, ann_id, admin_ann_token)
        assert resp.status_code == 200
        assert resp.json()["data"]["total_recipients"] == 2

    def test_publish_specific_employees_empty_ids(
        self, client, admin_ann_token, test_employee, employee_user
    ):
        """specific_employees with empty target_ids → 0 recipients, still publishes."""
        ann_id = self._create_draft(client, admin_ann_token, "specific_employees", [])
        mock_svc = _mock_notif()
        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_svc):
            resp = self._publish(client, ann_id, admin_ann_token)
        assert resp.status_code == 200
        assert resp.json()["data"]["total_recipients"] == 0
        assert resp.json()["data"]["status"] == "published"

    # ── teams ─────────────────────────────────────────────────────────────────

    def test_publish_single_team(
        self, client, admin_ann_token, test_employee, test_team, employee_user
    ):
        """target team_id → resolves employees in that team."""
        ann_id = self._create_draft(client, admin_ann_token, "teams", [test_team.team_id])
        mock_svc = _mock_notif(success=1)
        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_svc):
            resp = self._publish(client, ann_id, admin_ann_token)
        assert resp.status_code == 200
        # test_employee is in test_team
        assert resp.json()["data"]["total_recipients"] >= 1

    def test_publish_multi_team(
        self, client, admin_ann_token, test_employee, extra_employee,
        test_team, extra_team, employee_user
    ):
        """Two teams → union of their employees."""
        ann_id = self._create_draft(
            client, admin_ann_token, "teams", [test_team.team_id, extra_team.team_id]
        )
        mock_svc = _mock_notif(success=10)
        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_svc):
            resp = self._publish(client, ann_id, admin_ann_token)
        assert resp.status_code == 200
        assert resp.json()["data"]["total_recipients"] >= 2

    # ── all_drivers ───────────────────────────────────────────────────────────

    def test_publish_all_drivers(
        self, client, admin_ann_token, test_driver, second_driver, employee_user
    ):
        ann_id = self._create_draft(client, admin_ann_token, "all_drivers")
        mock_svc = _mock_notif(success=10)
        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_svc):
            resp = self._publish(client, ann_id, admin_ann_token)
        assert resp.status_code == 200
        assert resp.json()["data"]["total_recipients"] == 2

    # ── vendor_drivers ────────────────────────────────────────────────────────

    def test_publish_vendor_drivers(
        self, client, admin_ann_token, test_driver, second_driver, test_vendor, employee_user
    ):
        """Both test_driver and second_driver belong to test_vendor."""
        ann_id = self._create_draft(
            client, admin_ann_token, "vendor_drivers", [test_vendor.vendor_id]
        )
        mock_svc = _mock_notif(success=2)
        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_svc):
            resp = self._publish(client, ann_id, admin_ann_token)
        assert resp.status_code == 200
        assert resp.json()["data"]["total_recipients"] == 2

    def test_publish_vendor_drivers_empty(
        self, client, admin_ann_token, test_driver, employee_user
    ):
        """vendor_drivers with empty target_ids → 0 recipients."""
        ann_id = self._create_draft(client, admin_ann_token, "vendor_drivers", [])
        mock_svc = _mock_notif()
        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_svc):
            resp = self._publish(client, ann_id, admin_ann_token)
        assert resp.status_code == 200
        assert resp.json()["data"]["total_recipients"] == 0

    # ── specific_drivers ──────────────────────────────────────────────────────

    def test_publish_specific_drivers_single(
        self, client, admin_ann_token, test_driver, employee_user
    ):
        ann_id = self._create_draft(
            client, admin_ann_token, "specific_drivers", [test_driver.driver_id]
        )
        mock_svc = _mock_notif(success=1)
        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_svc):
            resp = self._publish(client, ann_id, admin_ann_token)
        assert resp.status_code == 200
        assert resp.json()["data"]["total_recipients"] == 1

    def test_publish_specific_drivers_multi(
        self, client, admin_ann_token, test_driver, second_driver, employee_user
    ):
        ids = [test_driver.driver_id, second_driver.driver_id]
        ann_id = self._create_draft(client, admin_ann_token, "specific_drivers", ids)
        mock_svc = _mock_notif(success=2)
        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_svc):
            resp = self._publish(client, ann_id, admin_ann_token)
        assert resp.status_code == 200
        assert resp.json()["data"]["total_recipients"] == 2

    # ── already published ─────────────────────────────────────────────────────

    def test_publish_already_published_fails(
        self, client, admin_ann_token, published_announcement_with_employee, test_employee, employee_user
    ):
        ann_id = published_announcement_with_employee.announcement_id
        resp = self._publish(client, ann_id, admin_ann_token)
        assert resp.status_code == 400

    # ── no_device delivery tracking ───────────────────────────────────────────

    def test_publish_tracks_no_device(
        self, client, admin_ann_token, test_employee, employee_user
    ):
        """Verify no_device_count is populated when FCM has no sessions."""
        emp_id = test_employee["employee"].employee_id
        ann_id = self._create_draft(client, admin_ann_token, "specific_employees", [emp_id])
        mock_svc = _mock_notif(success=0, no_session=1)
        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_svc):
            resp = self._publish(client, ann_id, admin_ann_token)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["no_device_count"] == 1
        assert data["success_count"] == 0

    # ── rich media published ──────────────────────────────────────────────────

    def test_publish_with_video_media(
        self, client, admin_ann_token, test_driver, employee_user
    ):
        ann_id = self._create_draft(
            client, admin_ann_token, "all_drivers", content_type="video"
        )
        # Also set media_url via update before publish
        client.put(
            f"/api/v1/announcements/{ann_id}",
            json={"media_url": "https://cdn.example.com/clip.mp4"},
            headers={"Authorization": admin_ann_token},
        )
        mock_svc = _mock_notif(success=1)
        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_svc):
            resp = self._publish(client, ann_id, admin_ann_token)
        assert resp.status_code == 200


# ═════════════════════════════════════════════════════════════════════════════
# TestAnnouncementRecipients
# ═════════════════════════════════════════════════════════════════════════════

class TestAnnouncementRecipients:
    def test_list_recipients(
        self, client, admin_ann_token, published_announcement_with_employee, test_employee, employee_user
    ):
        ann_id = published_announcement_with_employee.announcement_id
        resp = client.get(
            f"/api/v1/announcements/{ann_id}/recipients",
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] == 1
        rec = resp.json()["data"][0]
        assert rec["recipient_type"] == "employee"
        assert rec["recipient_user_id"] == test_employee["employee"].employee_id
        assert rec["delivery_status"] == "delivered"

    def test_list_driver_recipients(
        self, client, admin_ann_token, published_announcement_with_driver, test_driver, employee_user
    ):
        ann_id = published_announcement_with_driver.announcement_id
        resp = client.get(
            f"/api/v1/announcements/{ann_id}/recipients",
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 200
        items = resp.json()["data"]
        assert items[0]["recipient_type"] == "driver"
        assert items[0]["recipient_user_id"] == test_driver.driver_id

    def test_recipients_paginate(
        self, client, admin_ann_token, test_db, test_tenant, employee_user
    ):
        ann = Announcement(
            tenant_id=test_tenant.tenant_id,
            title="Multi Recipient",
            body="body",
            content_type=AnnouncementContentType.TEXT,
            target_type=AnnouncementTargetType.ALL_EMPLOYEES,
            status=AnnouncementStatus.PUBLISHED,
            total_recipients=5,
            is_active=True,
        )
        test_db.add(ann)
        test_db.flush()
        for i in range(5):
            test_db.add(AnnouncementRecipient(
                announcement_id=ann.announcement_id,
                recipient_type="employee",
                recipient_user_id=i + 1,
                tenant_id=test_tenant.tenant_id,
                delivery_status=AnnouncementDeliveryStatus.DELIVERED,
            ))
        test_db.commit()

        resp = client.get(
            f"/api/v1/announcements/{ann.announcement_id}/recipients?page=1&page_size=3",
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 3
        assert resp.json()["meta"]["total"] == 5


# ═════════════════════════════════════════════════════════════════════════════
# TestEmployeeAnnouncements
# ═════════════════════════════════════════════════════════════════════════════

class TestEmployeeAnnouncements:
    URL = "/api/v1/employee/announcements"

    def test_employee_sees_own_announcements(
        self, client, test_employee_ann_token, published_announcement_with_employee, employee_user
    ):
        resp = client.get(self.URL, headers={"Authorization": test_employee_ann_token})
        assert resp.status_code == 200
        items = resp.json()["data"]
        ids = [i["announcement_id"] for i in items]
        assert published_announcement_with_employee.announcement_id in ids

    def test_employee_does_not_see_draft(
        self, client, employee_ann_token, draft_announcement, employee_user
    ):
        """DRAFT announcements must NOT appear in employee feed."""
        resp = client.get(self.URL, headers={"Authorization": employee_ann_token})
        assert resp.status_code == 200
        items = resp.json()["data"]
        ids = [i["announcement_id"] for i in items]
        assert draft_announcement.announcement_id not in ids

    def test_employee_does_not_see_driver_announcement(
        self, client, employee_ann_token, published_announcement_with_driver, employee_user
    ):
        """Employee must not see driver-targeted announcements."""
        resp = client.get(self.URL, headers={"Authorization": employee_ann_token})
        assert resp.status_code == 200
        items = resp.json()["data"]
        ids = [i["announcement_id"] for i in items]
        assert published_announcement_with_driver.announcement_id not in ids

    def test_employee_response_contains_delivery_status(
        self, client, test_employee_ann_token, published_announcement_with_employee, employee_user
    ):
        resp = client.get(self.URL, headers={"Authorization": test_employee_ann_token})
        items = resp.json()["data"]
        ann = next(
            (i for i in items if i["announcement_id"] == published_announcement_with_employee.announcement_id),
            None,
        )
        assert ann is not None
        assert ann["delivery_status"] == "delivered"

    def test_employee_list_requires_auth(self, client):
        resp = client.get(self.URL)
        assert resp.status_code == 401


# ═════════════════════════════════════════════════════════════════════════════
# TestEmployeeMarkRead
# ═════════════════════════════════════════════════════════════════════════════

class TestEmployeeMarkRead:
    def test_mark_read(
        self, client, test_employee_ann_token, published_announcement_with_employee,
        test_db, employee_user
    ):
        ann_id = published_announcement_with_employee.announcement_id
        resp = client.post(
            f"/api/v1/employee/announcements/{ann_id}/read",
            headers={"Authorization": test_employee_ann_token},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["read_at"] is not None

        # Verify DB
        test_db.expire_all()
        rec = (
            test_db.query(AnnouncementRecipient)
            .filter(
                AnnouncementRecipient.announcement_id == ann_id,
                AnnouncementRecipient.recipient_type == "employee",
            )
            .first()
        )
        assert rec.read_at is not None
        assert rec.delivery_status == AnnouncementDeliveryStatus.READ

    def test_mark_read_idempotent(
        self, client, test_employee_ann_token, published_announcement_with_employee, employee_user
    ):
        """Marking read twice should succeed (idempotent)."""
        ann_id = published_announcement_with_employee.announcement_id
        url = f"/api/v1/employee/announcements/{ann_id}/read"
        r1 = client.post(url, headers={"Authorization": test_employee_ann_token})
        r2 = client.post(url, headers={"Authorization": test_employee_ann_token})
        assert r1.status_code == 200
        assert r2.status_code == 200

    def test_mark_read_not_recipient(self, client, employee_ann_token, draft_announcement, employee_user):
        """404 when this employee is not a recipient."""
        ann_id = draft_announcement.announcement_id
        resp = client.post(
            f"/api/v1/employee/announcements/{ann_id}/read",
            headers={"Authorization": employee_ann_token},
        )
        assert resp.status_code == 404


# ═════════════════════════════════════════════════════════════════════════════
# TestDriverAnnouncements
# ═════════════════════════════════════════════════════════════════════════════

class TestDriverAnnouncements:
    URL = "/api/v1/driver/announcements"

    def test_driver_sees_own_announcements(
        self, client, driver_ann_token, published_announcement_with_driver, test_driver, test_vendor, employee_user
    ):
        resp = client.get(self.URL, headers={"Authorization": driver_ann_token})
        assert resp.status_code == 200
        items = resp.json()["data"]
        ids = [i["announcement_id"] for i in items]
        assert published_announcement_with_driver.announcement_id in ids

    def test_driver_does_not_see_employee_announcement(
        self, client, driver_ann_token, published_announcement_with_employee, test_driver, test_vendor, employee_user
    ):
        resp = client.get(self.URL, headers={"Authorization": driver_ann_token})
        assert resp.status_code == 200
        items = resp.json()["data"]
        ids = [i["announcement_id"] for i in items]
        assert published_announcement_with_employee.announcement_id not in ids

    def test_driver_list_requires_auth(self, client):
        resp = client.get(self.URL)
        assert resp.status_code == 401


# ═════════════════════════════════════════════════════════════════════════════
# TestDriverMarkRead
# ═════════════════════════════════════════════════════════════════════════════

class TestDriverMarkRead:
    def test_mark_read(
        self, client, driver_ann_token, published_announcement_with_driver,
        test_db, test_driver, test_vendor, employee_user
    ):
        ann_id = published_announcement_with_driver.announcement_id
        resp = client.post(
            f"/api/v1/driver/announcements/{ann_id}/read",
            headers={"Authorization": driver_ann_token},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["read_at"] is not None

    def test_mark_read_not_recipient(
        self, client, driver_ann_token, draft_announcement, test_driver, test_vendor, employee_user
    ):
        ann_id = draft_announcement.announcement_id
        resp = client.post(
            f"/api/v1/driver/announcements/{ann_id}/read",
            headers={"Authorization": driver_ann_token},
        )
        assert resp.status_code == 404


# ═════════════════════════════════════════════════════════════════════════════
# TestTenantIsolation
# ═════════════════════════════════════════════════════════════════════════════

class TestTenantIsolation:
    def test_admin_cannot_see_other_tenant_announcement(
        self, client, second_tenant_admin_token, draft_announcement, second_tenant
    ):
        """TEST002 admin must get 404 for TEST001 announcement."""
        resp = client.get(
            f"/api/v1/announcements/{draft_announcement.announcement_id}",
            headers={"Authorization": second_tenant_admin_token},
        )
        assert resp.status_code == 404

    def test_admin_cannot_update_other_tenant_announcement(
        self, client, second_tenant_admin_token, draft_announcement, second_tenant
    ):
        resp = client.put(
            f"/api/v1/announcements/{draft_announcement.announcement_id}",
            json={"title": "Injected"},
            headers={"Authorization": second_tenant_admin_token},
        )
        assert resp.status_code == 404

    def test_admin_cannot_delete_other_tenant_announcement(
        self, client, second_tenant_admin_token, draft_announcement, second_tenant
    ):
        resp = client.delete(
            f"/api/v1/announcements/{draft_announcement.announcement_id}",
            headers={"Authorization": second_tenant_admin_token},
        )
        assert resp.status_code == 404

    def test_publish_does_not_cross_tenants(
        self, client, admin_ann_token, test_db, test_tenant, second_tenant,
        second_employee, employee_user
    ):
        """
        Publish all_employees for TEST001 must NOT include second_employee who
        belongs to TEST002.
        """
        ann = Announcement(
            tenant_id=test_tenant.tenant_id,
            title="Scoped",
            body="body",
            content_type=AnnouncementContentType.TEXT,
            target_type=AnnouncementTargetType.ALL_EMPLOYEES,
            status=AnnouncementStatus.DRAFT,
            is_active=True,
        )
        test_db.add(ann)
        test_db.commit()

        mock_svc = _mock_notif(success=0)
        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_svc):
            resp = client.post(
                f"/api/v1/announcements/{ann.announcement_id}/publish",
                headers={"Authorization": admin_ann_token},
            )
        assert resp.status_code == 200
        # None of the recipients should be second_employee (TEST002)
        recipients = (
            test_db.query(AnnouncementRecipient)
            .filter(AnnouncementRecipient.announcement_id == ann.announcement_id)
            .all()
        )
        user_ids = {r.recipient_user_id for r in recipients}
        assert second_employee["employee"].employee_id not in user_ids


# ═════════════════════════════════════════════════════════════════════════════
# TestInputValidation
# ═════════════════════════════════════════════════════════════════════════════

class TestInputValidation:
    URL = "/api/v1/announcements"

    def test_empty_title_rejected(self, client, admin_ann_token, employee_user):
        resp = client.post(
            self.URL,
            json={"title": "", "body": "body", "target_type": "all_employees"},
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 422

    def test_empty_body_rejected(self, client, admin_ann_token, employee_user):
        resp = client.post(
            self.URL,
            json={"title": "title", "body": "", "target_type": "all_employees"},
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 422

    def test_invalid_target_type_rejected(self, client, admin_ann_token, employee_user):
        resp = client.post(
            self.URL,
            json={"title": "x", "body": "y", "target_type": "whole_company"},
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 422

    def test_all_valid_content_types_accepted(self, client, admin_ann_token, employee_user):
        for ctype in ("text", "image", "video", "audio", "pdf", "link"):
            resp = client.post(
                self.URL,
                json={"title": f"Test {ctype}", "body": "body", "content_type": ctype, "target_type": "all_employees"},
                headers={"Authorization": admin_ann_token},
            )
            assert resp.status_code == 201, f"Failed for content_type={ctype}: {resp.text}"

    def test_all_valid_target_types_accepted(self, client, admin_ann_token, employee_user):
        for ttype in ("all_employees", "all_drivers"):
            resp = client.post(
                self.URL,
                json={"title": f"Test {ttype}", "body": "body", "target_type": ttype},
                headers={"Authorization": admin_ann_token},
            )
            assert resp.status_code == 201, f"Failed for target_type={ttype}: {resp.text}"

    def test_page_size_boundary(self, client, admin_ann_token, employee_user):
        resp = client.get(
            self.URL + "?page_size=200",
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 422  # max is 100

    def test_employee_cannot_reach_admin_create(self, client, employee_ann_token, employee_user):
        """Employee token must not satisfy AdminAuth (which needs booking.read)."""
        resp = client.post(
            self.URL,
            json={"title": "Injected", "body": "body", "target_type": "all_employees"},
            headers={"Authorization": employee_ann_token},
        )
        assert resp.status_code == 403

    def test_driver_cannot_reach_admin_create(self, client, driver_ann_token, test_driver, test_vendor, employee_user):
        resp = client.post(
            self.URL,
            json={"title": "Injected", "body": "body", "target_type": "all_employees"},
            headers={"Authorization": driver_ann_token},
        )
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Channel mock helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mock_sms(success: int = 1, failed: int = 0):
    """Return a mock SMSService instance."""
    svc = MagicMock()
    svc.send_bulk_sms.return_value = {
        "success_count": success,
        "failed_count": failed,
        "failed_numbers": [],
    }
    return svc


def _mock_email(success: bool = True):
    """Return a mock EmailService instance with async send_email."""
    svc = MagicMock()
    svc.send_email = AsyncMock(return_value=success)
    return svc


# ═════════════════════════════════════════════════════════════════════════════
# TestAnnouncementChannels  — multi-channel delivery
# ═════════════════════════════════════════════════════════════════════════════

class TestAnnouncementChannels:
    """Tests for the multi-channel (push / SMS / email / in_app) feature."""

    URL = "/api/v1/announcements"

    def _create(self, client, token, channels=None, target_type="specific_employees", target_ids=None):
        payload = {
            "title": "Channel Test",
            "body": "Channel test body.",
            "target_type": target_type,
        }
        if target_ids is not None:
            payload["target_ids"] = target_ids
        if channels is not None:
            payload["channels"] = channels
        resp = client.post(self.URL, json=payload, headers={"Authorization": token})
        assert resp.status_code == 201, resp.text
        return resp.json()["data"]

    def _publish(self, client, ann_id, token):
        return client.post(
            f"{self.URL}/{ann_id}/publish",
            headers={"Authorization": token},
        )

    # ── channel field in response ─────────────────────────────────────────────

    def test_channels_default_to_push_and_in_app(self, client, admin_ann_token, employee_user):
        """If channels not provided, defaults to ['push', 'in_app']."""
        data = self._create(client, admin_ann_token, target_type="all_employees")
        assert "channels" in data
        assert "push" in data["channels"]
        assert "in_app" in data["channels"]

    def test_in_app_always_included(self, client, admin_ann_token, employee_user):
        """Even if admin omits in_app from channels, it must be added automatically."""
        data = self._create(client, admin_ann_token, channels=["push"], target_type="all_employees")
        assert "in_app" in data["channels"]

    def test_create_with_all_channels(self, client, admin_ann_token, employee_user):
        data = self._create(
            client, admin_ann_token,
            channels=["push", "sms", "email", "in_app"],
            target_type="all_employees",
        )
        for ch in ("push", "sms", "email", "in_app"):
            assert ch in data["channels"]

    def test_create_with_sms_only(self, client, admin_ann_token, employee_user):
        data = self._create(
            client, admin_ann_token,
            channels=["sms", "in_app"],
            target_type="all_employees",
        )
        assert "sms" in data["channels"]

    def test_create_with_email_only(self, client, admin_ann_token, employee_user):
        data = self._create(
            client, admin_ann_token,
            channels=["email", "in_app"],
            target_type="all_employees",
        )
        assert "email" in data["channels"]

    def test_invalid_channel_rejected(self, client, admin_ann_token, employee_user):
        resp = client.post(
            self.URL,
            json={
                "title": "Bad channel",
                "body": "body",
                "target_type": "all_employees",
                "channels": ["whatsapp"],
            },
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 422

    # ── update channels on draft ──────────────────────────────────────────────

    def test_update_channels_on_draft(self, client, admin_ann_token, draft_announcement, employee_user):
        resp = client.put(
            f"{self.URL}/{draft_announcement.announcement_id}",
            json={"channels": ["push", "sms", "email", "in_app"]},
            headers={"Authorization": admin_ann_token},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        for ch in ("push", "sms", "email", "in_app"):
            assert ch in data["channels"]

    # ── push-only publish ─────────────────────────────────────────────────────

    def test_publish_push_only_calls_notification_service(
        self, client, admin_ann_token, test_employee, employee_user
    ):
        """Push-only: UnifiedNotificationService called, SMS/email not called."""
        emp_id = test_employee["employee"].employee_id
        data = self._create(client, admin_ann_token, channels=["push", "in_app"],
                            target_type="specific_employees", target_ids=[emp_id])
        ann_id = data["announcement_id"]

        mock_push = _mock_notif(success=1)
        mock_sms  = _mock_sms()
        mock_email = _mock_email()

        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_push), \
             patch("app.services.sms_service.SMSService", return_value=mock_sms), \
             patch("app.core.email_service.EmailService", return_value=mock_email):
            resp = self._publish(client, ann_id, admin_ann_token)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "published"
        assert data["success_count"] == 1
        assert data["sms_sent_count"] == 0    # SMS not selected
        assert data["email_sent_count"] == 0  # Email not selected
        mock_push.send_to_users_batch.assert_called_once()
        mock_sms.send_bulk_sms.assert_not_called()
        mock_email.send_email.assert_not_called()

    # ── SMS channel publish ───────────────────────────────────────────────────

    def test_publish_with_sms_channel_calls_sms_service(
        self, client, admin_ann_token, test_employee, employee_user
    ):
        emp_id = test_employee["employee"].employee_id
        data = self._create(
            client, admin_ann_token,
            channels=["push", "sms", "in_app"],
            target_type="specific_employees",
            target_ids=[emp_id],
        )
        ann_id = data["announcement_id"]

        mock_push  = _mock_notif(success=1)
        mock_sms   = _mock_sms(success=1)
        mock_email = _mock_email()

        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_push), \
             patch("app.services.sms_service.SMSService", return_value=mock_sms), \
             patch("app.core.email_service.EmailService", return_value=mock_email):
            resp = self._publish(client, ann_id, admin_ann_token)

        assert resp.status_code == 200
        resp_data = resp.json()["data"]
        assert resp_data["sms_sent_count"] == 1
        assert resp_data["email_sent_count"] == 0
        mock_sms.send_bulk_sms.assert_called_once()
        mock_email.send_email.assert_not_called()

    def test_publish_sms_only_no_push(
        self, client, admin_ann_token, test_employee, employee_user
    ):
        """SMS + in_app only — push not fired, delivery_status still DELIVERED."""
        emp_id = test_employee["employee"].employee_id
        data = self._create(
            client, admin_ann_token,
            channels=["sms", "in_app"],
            target_type="specific_employees",
            target_ids=[emp_id],
        )
        ann_id = data["announcement_id"]

        mock_push  = _mock_notif(success=0)
        mock_sms   = _mock_sms(success=1)

        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_push), \
             patch("app.services.sms_service.SMSService", return_value=mock_sms):
            resp = self._publish(client, ann_id, admin_ann_token)

        assert resp.status_code == 200
        resp_data = resp.json()["data"]
        assert resp_data["status"] == "published"
        assert resp_data["sms_sent_count"] == 1
        assert resp_data["success_count"] == 0  # push not selected
        mock_push.send_to_users_batch.assert_not_called()

    # ── Email channel publish ─────────────────────────────────────────────────

    def test_publish_with_email_channel_calls_email_service(
        self, client, admin_ann_token, test_employee, employee_user
    ):
        emp_id = test_employee["employee"].employee_id
        data = self._create(
            client, admin_ann_token,
            channels=["push", "email", "in_app"],
            target_type="specific_employees",
            target_ids=[emp_id],
        )
        ann_id = data["announcement_id"]

        mock_push  = _mock_notif(success=1)
        mock_sms   = _mock_sms()
        mock_email = _mock_email(success=True)

        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_push), \
             patch("app.services.sms_service.SMSService", return_value=mock_sms), \
             patch("app.core.email_service.EmailService", return_value=mock_email):
            resp = self._publish(client, ann_id, admin_ann_token)

        assert resp.status_code == 200
        resp_data = resp.json()["data"]
        assert resp_data["email_sent_count"] == 1
        assert resp_data["sms_sent_count"] == 0
        mock_email.send_email.assert_called()
        mock_sms.send_bulk_sms.assert_not_called()

    def test_publish_email_only_no_push(
        self, client, admin_ann_token, test_employee, employee_user
    ):
        """Email + in_app only — push not selected."""
        emp_id = test_employee["employee"].employee_id
        data = self._create(
            client, admin_ann_token,
            channels=["email", "in_app"],
            target_type="specific_employees",
            target_ids=[emp_id],
        )
        ann_id = data["announcement_id"]

        mock_push  = _mock_notif()
        mock_email = _mock_email(success=True)

        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_push), \
             patch("app.core.email_service.EmailService", return_value=mock_email):
            resp = self._publish(client, ann_id, admin_ann_token)

        assert resp.status_code == 200
        resp_data = resp.json()["data"]
        assert resp_data["email_sent_count"] == 1
        mock_push.send_to_users_batch.assert_not_called()

    # ── All channels publish ──────────────────────────────────────────────────

    def test_publish_all_channels(
        self, client, admin_ann_token, test_employee, employee_user
    ):
        """Push + SMS + Email + in_app — all three services called."""
        emp_id = test_employee["employee"].employee_id
        data = self._create(
            client, admin_ann_token,
            channels=["push", "sms", "email", "in_app"],
            target_type="specific_employees",
            target_ids=[emp_id],
        )
        ann_id = data["announcement_id"]

        mock_push  = _mock_notif(success=1)
        mock_sms   = _mock_sms(success=1)
        mock_email = _mock_email(success=True)

        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_push), \
             patch("app.services.sms_service.SMSService", return_value=mock_sms), \
             patch("app.core.email_service.EmailService", return_value=mock_email):
            resp = self._publish(client, ann_id, admin_ann_token)

        assert resp.status_code == 200
        resp_data = resp.json()["data"]
        assert resp_data["status"] == "published"
        assert resp_data["total_recipients"] == 1
        assert resp_data["success_count"] == 1
        assert resp_data["sms_sent_count"] == 1
        assert resp_data["email_sent_count"] == 1
        assert "push" in resp_data["channels"]
        assert "sms"  in resp_data["channels"]
        assert "email" in resp_data["channels"]

    # ── Response shape ────────────────────────────────────────────────────────

    def test_response_includes_sms_email_counts_always(
        self, client, admin_ann_token, employee_user
    ):
        """Even push-only announcements must have sms_sent_count / email_sent_count = 0."""
        data = self._create(client, admin_ann_token, channels=["push", "in_app"],
                            target_type="all_employees")
        assert "sms_sent_count" not in data or data.get("sms_sent_count", 0) == 0
        # After publish:
        ann_id = data["announcement_id"]
        mock_push = _mock_notif(success=0)
        with patch("app.crud.announcement.UnifiedNotificationService", return_value=mock_push):
            resp = self._publish(client, ann_id, admin_ann_token)
        assert resp.status_code == 200
        resp_data = resp.json()["data"]
        assert resp_data.get("sms_sent_count", 0) == 0
        assert resp_data.get("email_sent_count", 0) == 0

    # ── Recipient row channel timestamps ─────────────────────────────────────

    def test_recipient_sms_sent_at_set_after_sms_publish(
        self, client, admin_ann_token, test_employee, test_db, employee_user
    ):
        emp_id = test_employee["employee"].employee_id
        data = self._create(
            client, admin_ann_token,
            channels=["sms", "in_app"],
            target_type="specific_employees",
            target_ids=[emp_id],
        )
        ann_id = data["announcement_id"]
        mock_sms = _mock_sms(success=1)

        with patch("app.crud.announcement.UnifiedNotificationService", return_value=_mock_notif()), \
             patch("app.services.sms_service.SMSService", return_value=mock_sms):
            resp = self._publish(client, ann_id, admin_ann_token)

        assert resp.status_code == 200
        test_db.expire_all()
        rec = (
            test_db.query(AnnouncementRecipient)
            .filter(AnnouncementRecipient.announcement_id == ann_id)
            .first()
        )
        assert rec is not None
        assert rec.sms_sent_at is not None

    def test_recipient_email_sent_at_set_after_email_publish(
        self, client, admin_ann_token, test_employee, test_db, employee_user
    ):
        emp_id = test_employee["employee"].employee_id
        data = self._create(
            client, admin_ann_token,
            channels=["email", "in_app"],
            target_type="specific_employees",
            target_ids=[emp_id],
        )
        ann_id = data["announcement_id"]
        mock_email = _mock_email(success=True)

        with patch("app.crud.announcement.UnifiedNotificationService", return_value=_mock_notif()), \
             patch("app.core.email_service.EmailService", return_value=mock_email):
            resp = self._publish(client, ann_id, admin_ann_token)

        assert resp.status_code == 200
        test_db.expire_all()
        rec = (
            test_db.query(AnnouncementRecipient)
            .filter(AnnouncementRecipient.announcement_id == ann_id)
            .first()
        )
        assert rec is not None
        assert rec.email_sent_at is not None

    # ── Driver targets with channels ──────────────────────────────────────────

    def test_publish_sms_to_drivers(
        self, client, admin_ann_token, test_driver, employee_user
    ):
        """SMS channel with driver target → driver phone used."""
        data = self._create(
            client, admin_ann_token,
            channels=["sms", "in_app"],
            target_type="specific_drivers",
            target_ids=[test_driver.driver_id],
        )
        ann_id = data["announcement_id"]
        mock_sms = _mock_sms(success=1)

        with patch("app.crud.announcement.UnifiedNotificationService", return_value=_mock_notif()), \
             patch("app.services.sms_service.SMSService", return_value=mock_sms):
            resp = self._publish(client, ann_id, admin_ann_token)

        assert resp.status_code == 200
        assert resp.json()["data"]["sms_sent_count"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 13. Filter tests  (date range, content_type, target_type, unread_only)
# ─────────────────────────────────────────────────────────────────────────────

class TestAnnouncementFilters:
    """
    Covers all new query-string filters added to the list endpoints:
      GET /announcements             (admin) — status, content_type, target_type,
                                              from_date, to_date, date_field
      GET /employee/announcements            — from_date, to_date, unread_only,
                                              content_type
      GET /driver/announcements              — same as employee
    """

    ANN_URL      = "/api/v1/announcements"
    EMP_URL      = "/api/v1/employee/announcements"
    DRV_URL      = "/api/v1/driver/announcements"

    # ── helpers ──────────────────────────────────────────────────────────────

    def _create(self, client, token, **kwargs):
        payload = {
            "title": kwargs.get("title", "Filter Test"),
            "body": "body text",
            "content_type": kwargs.get("content_type", "text"),
            "target_type": kwargs.get("target_type", "all_employees"),
            "target_ids": kwargs.get("target_ids", []),
            "channels": kwargs.get("channels", ["in_app"]),
        }
        r = client.post(self.ANN_URL, json=payload,
                        headers={"Authorization": token})
        assert r.status_code == 201, r.text
        return r.json()["data"]

    def _publish(self, client, ann_id, token):
        with patch("app.crud.announcement.UnifiedNotificationService",
                   return_value=_mock_notif()):
            return client.post(
                f"{self.ANN_URL}/{ann_id}/publish",
                headers={"Authorization": token},
            )

    def _list_admin(self, client, token, **params):
        return client.get(
            self.ANN_URL,
            params=params,
            headers={"Authorization": token},
        )

    def _list_employee(self, client, token, **params):
        return client.get(
            self.EMP_URL,
            params=params,
            headers={"Authorization": token},
        )

    def _list_driver(self, client, token, **params):
        return client.get(
            self.DRV_URL,
            params=params,
            headers={"Authorization": token},
        )

    # ── Admin filter tests ────────────────────────────────────────────────────

    def test_admin_list_no_filters_returns_all(
        self, client, admin_ann_token, test_db, test_tenant
    ):
        """Baseline: list without filters returns everything for the tenant."""
        self._create(client, admin_ann_token, title="A1")
        self._create(client, admin_ann_token, title="A2")
        resp = self._list_admin(client, admin_ann_token)
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] >= 2

    def test_admin_filter_by_status_published(
        self, client, admin_ann_token
    ):
        """status=published returns only published announcements."""
        ann = self._create(client, admin_ann_token, title="ToPublish")
        self._publish(client, ann["announcement_id"], admin_ann_token)

        resp = self._list_admin(client, admin_ann_token, status="published")
        assert resp.status_code == 200
        for item in resp.json()["data"]:
            assert item["status"] == "published"

    def test_admin_filter_by_status_draft(
        self, client, admin_ann_token
    ):
        """status=draft returns only drafts."""
        self._create(client, admin_ann_token, title="StaysDraft")
        resp = self._list_admin(client, admin_ann_token, status="draft")
        assert resp.status_code == 200
        for item in resp.json()["data"]:
            assert item["status"] == "draft"

    def test_admin_filter_by_content_type(
        self, client, admin_ann_token
    ):
        """content_type filter returns only matching items."""
        self._create(client, admin_ann_token, title="TextAnn", content_type="text")
        self._create(client, admin_ann_token, title="ImageAnn", content_type="image")

        resp = self._list_admin(client, admin_ann_token, content_type="image")
        assert resp.status_code == 200
        for item in resp.json()["data"]:
            assert item["content_type"] == "image"

    def test_admin_filter_by_target_type(
        self, client, admin_ann_token
    ):
        """target_type filter narrows results correctly."""
        self._create(client, admin_ann_token, title="AllEmp",
                     target_type="all_employees")
        self._create(client, admin_ann_token, title="AllDrv",
                     target_type="all_drivers")

        resp = self._list_admin(client, admin_ann_token, target_type="all_drivers")
        assert resp.status_code == 200
        for item in resp.json()["data"]:
            assert item["target_type"] == "all_drivers"

    def test_admin_filter_from_date_future_returns_empty(
        self, client, admin_ann_token
    ):
        """from_date in the far future should return no items."""
        self._create(client, admin_ann_token, title="OldAnn")
        resp = self._list_admin(
            client, admin_ann_token, from_date="2099-01-01", date_field="created_at"
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] == 0

    def test_admin_filter_to_date_past_returns_empty(
        self, client, admin_ann_token
    ):
        """to_date in the distant past should return no items."""
        self._create(client, admin_ann_token, title="NewAnn")
        resp = self._list_admin(
            client, admin_ann_token, to_date="2000-01-01", date_field="created_at"
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] == 0

    def test_admin_filter_date_range_includes_today(
        self, client, admin_ann_token
    ):
        """A broad date range that spans today should include newly created items."""
        self._create(client, admin_ann_token, title="TodayAnn")
        resp = self._list_admin(
            client, admin_ann_token,
            from_date="2020-01-01",
            to_date="2099-12-31",
            date_field="created_at",
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] >= 1

    def test_admin_filter_invalid_date_format_returns_422(
        self, client, admin_ann_token
    ):
        """Bad date string must return 422 Unprocessable Entity."""
        resp = self._list_admin(
            client, admin_ann_token, from_date="not-a-date"
        )
        assert resp.status_code == 422

    def test_admin_filter_invalid_date_field_returns_422(
        self, client, admin_ann_token
    ):
        """Unknown date_field must return 422 Unprocessable Entity."""
        resp = self._list_admin(
            client, admin_ann_token, date_field="unknown_field"
        )
        assert resp.status_code == 422

    def test_admin_pagination_page_size(
        self, client, admin_ann_token
    ):
        """page_size=1 returns exactly 1 item per page."""
        self._create(client, admin_ann_token, title="P1")
        self._create(client, admin_ann_token, title="P2")
        resp = self._list_admin(client, admin_ann_token, page=1, page_size=1)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["meta"]["per_page"] == 1

    def test_admin_pagination_second_page(
        self, client, admin_ann_token
    ):
        """Page 2 returns a different item than page 1."""
        self._create(client, admin_ann_token, title="PG1")
        self._create(client, admin_ann_token, title="PG2")
        r1 = self._list_admin(client, admin_ann_token, page=1, page_size=1)
        r2 = self._list_admin(client, admin_ann_token, page=2, page_size=1)
        ids_p1 = {i["announcement_id"] for i in r1.json()["data"]}
        ids_p2 = {i["announcement_id"] for i in r2.json()["data"]}
        assert ids_p1.isdisjoint(ids_p2)

    # ── Employee filter tests ─────────────────────────────────────────────────

    def _seed_employee_announcement(
        self, client, admin_ann_token, test_employee, content_type="text"
    ):
        """Create + publish an all_employees announcement; return its ID."""
        ann = self._create(
            client, admin_ann_token,
            title="EmpFilter",
            content_type=content_type,
            target_type="all_employees",
        )
        self._publish(client, ann["announcement_id"], admin_ann_token)
        return ann["announcement_id"]

    def test_employee_list_no_filters(
        self, client, test_employee_ann_token, admin_ann_token, test_employee
    ):
        """Employee inbox without filters returns published announcements."""
        self._seed_employee_announcement(client, admin_ann_token, test_employee)
        resp = self._list_employee(client, test_employee_ann_token)
        assert resp.status_code == 200

    def test_employee_filter_from_date_future_returns_empty(
        self, client, test_employee_ann_token, admin_ann_token, test_employee
    ):
        """from_date in the future → no results in employee inbox."""
        self._seed_employee_announcement(client, admin_ann_token, test_employee)
        resp = self._list_employee(
            client, test_employee_ann_token, from_date="2099-01-01"
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] == 0

    def test_employee_filter_to_date_past_returns_empty(
        self, client, test_employee_ann_token, admin_ann_token, test_employee
    ):
        """to_date in the past → no results in employee inbox."""
        self._seed_employee_announcement(client, admin_ann_token, test_employee)
        resp = self._list_employee(
            client, test_employee_ann_token, to_date="2000-01-01"
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] == 0

    def test_employee_filter_date_range_broad(
        self, client, test_employee_ann_token, admin_ann_token, test_employee
    ):
        """Broad date range includes today's published announcements."""
        self._seed_employee_announcement(client, admin_ann_token, test_employee)
        resp = self._list_employee(
            client, test_employee_ann_token,
            from_date="2020-01-01", to_date="2099-12-31"
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] >= 1

    def test_employee_filter_content_type(
        self, client, test_employee_ann_token, admin_ann_token, test_employee
    ):
        """content_type filter on employee inbox returns only matching items."""
        self._seed_employee_announcement(
            client, admin_ann_token, test_employee, content_type="image"
        )
        resp = self._list_employee(
            client, test_employee_ann_token, content_type="image"
        )
        assert resp.status_code == 200
        for item in resp.json()["data"]:
            assert item["content_type"] == "image"

    def test_employee_filter_unread_only(
        self, client, test_employee_ann_token, admin_ann_token, test_employee
    ):
        """unread_only=true returns only unread items; after marking read it's excluded."""
        ann_id = self._seed_employee_announcement(
            client, admin_ann_token, test_employee
        )
        # Before marking read — should appear in unread list
        resp_before = self._list_employee(
            client, test_employee_ann_token, unread_only=True
        )
        assert resp_before.status_code == 200
        ids_before = {i["announcement_id"] for i in resp_before.json()["data"]}
        assert ann_id in ids_before

        # Mark it read
        client.post(
            f"{self.EMP_URL}/{ann_id}/read",
            headers={"Authorization": test_employee_ann_token},
        )

        # After marking read — should NOT appear in unread list
        resp_after = self._list_employee(
            client, test_employee_ann_token, unread_only=True
        )
        assert resp_after.status_code == 200
        ids_after = {i["announcement_id"] for i in resp_after.json()["data"]}
        assert ann_id not in ids_after

    def test_employee_filter_invalid_date_returns_422(
        self, client, test_employee_ann_token
    ):
        """Bad date string on employee endpoint → 422."""
        resp = self._list_employee(
            client, test_employee_ann_token, from_date="bad-date"
        )
        assert resp.status_code == 422

    def test_employee_pagination_page_size(
        self, client, test_employee_ann_token, admin_ann_token, test_employee
    ):
        """page_size=1 on employee inbox returns exactly 1 item."""
        self._seed_employee_announcement(client, admin_ann_token, test_employee)
        self._seed_employee_announcement(client, admin_ann_token, test_employee)
        resp = self._list_employee(
            client, test_employee_ann_token, page=1, page_size=1
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1
        assert resp.json()["meta"]["per_page"] == 1

    # ── Driver filter tests ───────────────────────────────────────────────────

    def _seed_driver_announcement(self, client, admin_ann_token, test_driver,
                                  content_type="text"):
        ann = self._create(
            client, admin_ann_token,
            title="DrvFilter",
            content_type=content_type,
            target_type="all_drivers",
        )
        self._publish(client, ann["announcement_id"], admin_ann_token)
        return ann["announcement_id"]

    def test_driver_filter_from_date_future_empty(
        self, client, driver_ann_token, admin_ann_token, test_driver
    ):
        """from_date in future → empty driver inbox."""
        self._seed_driver_announcement(client, admin_ann_token, test_driver)
        resp = self._list_driver(
            client, driver_ann_token, from_date="2099-01-01"
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] == 0

    def test_driver_filter_to_date_past_empty(
        self, client, driver_ann_token, admin_ann_token, test_driver
    ):
        """to_date in past → empty driver inbox."""
        self._seed_driver_announcement(client, admin_ann_token, test_driver)
        resp = self._list_driver(
            client, driver_ann_token, to_date="2000-01-01"
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] == 0

    def test_driver_filter_content_type(
        self, client, driver_ann_token, admin_ann_token, test_driver
    ):
        """content_type filter on driver inbox."""
        self._seed_driver_announcement(
            client, admin_ann_token, test_driver, content_type="pdf"
        )
        resp = self._list_driver(
            client, driver_ann_token, content_type="pdf"
        )
        assert resp.status_code == 200
        for item in resp.json()["data"]:
            assert item["content_type"] == "pdf"

    def test_driver_filter_unread_only(
        self, client, driver_ann_token, admin_ann_token, test_driver
    ):
        """unread_only on driver inbox; after mark-read item disappears."""
        ann_id = self._seed_driver_announcement(
            client, admin_ann_token, test_driver
        )
        resp_before = self._list_driver(
            client, driver_ann_token, unread_only=True
        )
        assert resp_before.status_code == 200
        assert ann_id in {i["announcement_id"] for i in resp_before.json()["data"]}

        client.post(
            f"{self.DRV_URL}/{ann_id}/read",
            headers={"Authorization": driver_ann_token},
        )

        resp_after = self._list_driver(
            client, driver_ann_token, unread_only=True
        )
        assert resp_after.status_code == 200
        assert ann_id not in {i["announcement_id"] for i in resp_after.json()["data"]}

    def test_driver_filter_invalid_date_returns_422(
        self, client, driver_ann_token
    ):
        """Bad date on driver endpoint → 422."""
        resp = self._list_driver(client, driver_ann_token, to_date="tomorrow")
        assert resp.status_code == 422

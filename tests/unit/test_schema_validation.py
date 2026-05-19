"""
Unit tests for Pydantic schema validation.

Covers: EmployeeCreate, EmployeeUpdate, BookingCreate, BookingStatusEnum
Validates: field constraints, custom validators, error messages, edge cases.

No DB, no HTTP.
"""
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.booking import BookingCreate, BookingStatusEnum, BookingTypeEnum
from app.schemas.employee import EmployeeCreate, EmployeeUpdate, GenderEnum, SpecialNeedsEnum

pytestmark = pytest.mark.unit

# ─── Baseline payloads ────────────────────────────────────────────────────────
VALID_EMPLOYEE = {
    "name": "John Doe",
    "employee_code": "EMP001",
    "email": "john.doe@example.com",
    "phone": "+12125551234",
    "password": "SecurePass@123",
    "team_id": 1,
    "gender": "Male",
    "is_active": True,
}


def future(days: int = 1) -> date:
    return date.today() + timedelta(days=days)


# ─────────────────────────────────────────────────────────────────────────────
# EmployeeCreate
# ─────────────────────────────────────────────────────────────────────────────
class TestEmployeeCreateSchema:
    def test_valid_payload_passes(self):
        obj = EmployeeCreate(**VALID_EMPLOYEE)
        assert obj.name == "John Doe"
        assert obj.employee_code == "EMP001"

    # ── Email normalization ───────────────────────────────────────────────────
    def test_email_normalized_to_lowercase(self):
        obj = EmployeeCreate(**{**VALID_EMPLOYEE, "email": "JOHN.DOE@EXAMPLE.COM"})
        assert obj.email == "john.doe@example.com"

    def test_email_with_leading_whitespace_stripped(self):
        obj = EmployeeCreate(**{**VALID_EMPLOYEE, "email": "  john@example.com  "})
        assert obj.email == "john@example.com"

    def test_invalid_email_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc:
            EmployeeCreate(**{**VALID_EMPLOYEE, "email": "not-an-email"})
        assert any("email" in str(e).lower() for e in exc.value.errors())

    # ── Phone validation ─────────────────────────────────────────────────────
    def test_valid_e164_phone_formats(self):
        for phone in ["+12125551234", "+442012345678", "+919876543210"]:
            obj = EmployeeCreate(**{**VALID_EMPLOYEE, "phone": phone})
            assert obj.phone == phone

    def test_invalid_phone_format_raises_error(self):
        with pytest.raises(ValidationError) as exc:
            EmployeeCreate(**{**VALID_EMPLOYEE, "phone": "0123456789"})
        assert any(
            "E.164" in str(e) or "phone" in str(e).lower() for e in exc.value.errors()
        )

    def test_phone_without_plus_prefix_fails(self):
        with pytest.raises(ValidationError):
            EmployeeCreate(**{**VALID_EMPLOYEE, "phone": "12125551234"})

    # ── Password validation ───────────────────────────────────────────────────
    def test_weak_password_all_lowercase_fails(self):
        with pytest.raises(ValidationError):
            EmployeeCreate(**{**VALID_EMPLOYEE, "password": "weakpassword"})

    def test_password_missing_special_char_fails(self):
        with pytest.raises(ValidationError):
            EmployeeCreate(**{**VALID_EMPLOYEE, "password": "NoSpecial1"})

    def test_password_missing_digit_fails(self):
        with pytest.raises(ValidationError):
            EmployeeCreate(**{**VALID_EMPLOYEE, "password": "NoDigits!@#"})

    def test_strong_password_accepted(self):
        obj = EmployeeCreate(**{**VALID_EMPLOYEE, "password": "Str0ng@Pass!"})
        assert obj.password == "Str0ng@Pass!"

    # ── Name validation ───────────────────────────────────────────────────────
    def test_single_char_name_fails(self):
        with pytest.raises(ValidationError):
            EmployeeCreate(**{**VALID_EMPLOYEE, "name": "A"})

    def test_name_with_digits_fails(self):
        with pytest.raises(ValidationError):
            EmployeeCreate(**{**VALID_EMPLOYEE, "name": "John123"})

    def test_name_with_hyphen_and_apostrophe_allowed(self):
        obj = EmployeeCreate(**{**VALID_EMPLOYEE, "name": "O'Brien-Smith"})
        assert obj.name == "O'Brien-Smith"

    # ── Gender normalization ──────────────────────────────────────────────────
    def test_gender_case_insensitive_male(self):
        for variant in ["male", "MALE", "Male"]:
            obj = EmployeeCreate(**{**VALID_EMPLOYEE, "gender": variant})
            assert obj.gender == GenderEnum.MALE

    def test_gender_female_accepted(self):
        obj = EmployeeCreate(**{**VALID_EMPLOYEE, "gender": "Female"})
        assert obj.gender == GenderEnum.FEMALE

    def test_gender_other_accepted(self):
        obj = EmployeeCreate(**{**VALID_EMPLOYEE, "gender": "Other"})
        assert obj.gender == GenderEnum.OTHER

    def test_blank_gender_normalizes_to_none(self):
        obj = EmployeeCreate(**{**VALID_EMPLOYEE, "gender": "  "})
        assert obj.gender is None

    # ── Coordinate validation ─────────────────────────────────────────────────
    def test_valid_lat_lng_accepted(self):
        obj = EmployeeCreate(
            **{**VALID_EMPLOYEE, "latitude": 12.9716, "longitude": 77.5946}
        )
        assert obj.latitude == 12.9716

    def test_latitude_out_of_range_fails(self):
        with pytest.raises(ValidationError):
            EmployeeCreate(**{**VALID_EMPLOYEE, "latitude": 91.0})

    def test_longitude_out_of_range_fails(self):
        with pytest.raises(ValidationError):
            EmployeeCreate(**{**VALID_EMPLOYEE, "longitude": 181.0})

    def test_coordinate_as_string_coerced_to_float(self):
        obj = EmployeeCreate(
            **{**VALID_EMPLOYEE, "latitude": "12.9716", "longitude": "77.5946"}
        )
        assert isinstance(obj.latitude, float)

    # ── Address constraint ────────────────────────────────────────────────────
    def test_address_over_250_chars_fails(self):
        with pytest.raises(ValidationError) as exc:
            EmployeeCreate(**{**VALID_EMPLOYEE, "address": "A" * 251})
        assert any("250" in str(e) or "address" in str(e).lower() for e in exc.value.errors())

    def test_address_exactly_250_chars_passes(self):
        obj = EmployeeCreate(**{**VALID_EMPLOYEE, "address": "A" * 250})
        assert len(obj.address) == 250

    # ── Missing required fields ───────────────────────────────────────────────
    @pytest.mark.parametrize("field", ["name", "email", "phone", "employee_code", "password"])
    def test_missing_required_field_raises_error(self, field):
        payload = {k: v for k, v in VALID_EMPLOYEE.items() if k != field}
        with pytest.raises(ValidationError):
            EmployeeCreate(**payload)

    # ── Special needs date cross-validation ──────────────────────────────────
    def test_special_needs_requires_dates(self):
        with pytest.raises(ValidationError) as exc:
            EmployeeCreate(
                **{**VALID_EMPLOYEE, "special_needs": "Wheelchair"}
            )
        assert any(
            "date" in str(e).lower() or "start" in str(e).lower()
            for e in exc.value.errors()
        )

    def test_special_needs_with_valid_future_dates(self):
        obj = EmployeeCreate(
            **{
                **VALID_EMPLOYEE,
                "special_needs": "Wheelchair",
                "special_needs_start_date": future(1),
                "special_needs_end_date": future(30),
            }
        )
        assert obj.special_needs == SpecialNeedsEnum.WHEELCHAIR

    def test_special_needs_end_before_start_fails(self):
        with pytest.raises(ValidationError):
            EmployeeCreate(
                **{
                    **VALID_EMPLOYEE,
                    "special_needs": "Pregnant",
                    "special_needs_start_date": future(10),
                    "special_needs_end_date": future(5),
                }
            )

    def test_no_special_needs_clears_dates(self):
        obj = EmployeeCreate(
            **{
                **VALID_EMPLOYEE,
                "special_needs": None,
                "special_needs_start_date": future(1),
                "special_needs_end_date": future(30),
            }
        )
        assert obj.special_needs_start_date is None
        assert obj.special_needs_end_date is None


# ─────────────────────────────────────────────────────────────────────────────
# EmployeeUpdate (partial schema)
# ─────────────────────────────────────────────────────────────────────────────
class TestEmployeeUpdateSchema:
    def test_all_fields_optional(self):
        """EmployeeUpdate with no fields must not raise."""
        obj = EmployeeUpdate()
        assert obj.name is None

    def test_partial_update_accepted(self):
        obj = EmployeeUpdate(name="Jane Doe", is_active=False)
        assert obj.name == "Jane Doe"
        assert obj.is_active is False

    def test_email_normalized_in_update(self):
        obj = EmployeeUpdate(email="JANE@EXAMPLE.COM")
        assert obj.email == "jane@example.com"

    def test_weak_password_rejected_in_update(self):
        with pytest.raises(ValidationError):
            EmployeeUpdate(password="weak")


# ─────────────────────────────────────────────────────────────────────────────
# BookingCreate
# ─────────────────────────────────────────────────────────────────────────────
class TestBookingCreateSchema:
    def test_valid_payload_passes(self):
        obj = BookingCreate(
            employee_id=1, shift_id=20, booking_dates=[future(1), future(2)]
        )
        assert obj.employee_id == 1
        assert obj.shift_id == 20

    def test_booking_type_defaults_to_regular(self):
        obj = BookingCreate(employee_id=1, shift_id=20, booking_dates=[future()])
        assert obj.booking_type == BookingTypeEnum.REGULAR

    def test_adhoc_booking_type_accepted(self):
        obj = BookingCreate(
            employee_id=1, shift_id=20, booking_dates=[future()], booking_type="adhoc"
        )
        assert obj.booking_type == BookingTypeEnum.ADHOC

    def test_medical_emergency_type_accepted(self):
        obj = BookingCreate(
            employee_id=1,
            shift_id=20,
            booking_dates=[future()],
            booking_type="medical_emergency",
        )
        assert obj.booking_type == BookingTypeEnum.MEDICAL_EMERGENCY

    def test_invalid_booking_type_raises_error(self):
        with pytest.raises(ValidationError):
            BookingCreate(
                employee_id=1,
                shift_id=20,
                booking_dates=[future()],
                booking_type="invalid_type",
            )

    def test_missing_employee_id_raises_error(self):
        with pytest.raises(ValidationError):
            BookingCreate(shift_id=20, booking_dates=[future()])

    def test_missing_shift_id_raises_error(self):
        with pytest.raises(ValidationError):
            BookingCreate(employee_id=1, booking_dates=[future()])

    def test_empty_booking_dates_raises_error(self):
        with pytest.raises(ValidationError):
            BookingCreate(employee_id=1, shift_id=20, booking_dates=[])

    def test_multiple_future_dates_accepted(self):
        dates = [future(i) for i in range(1, 8)]  # 7 days
        obj = BookingCreate(employee_id=1, shift_id=20, booking_dates=dates)
        assert len(obj.booking_dates) == 7


# ─────────────────────────────────────────────────────────────────────────────
# BookingStatusEnum
# ─────────────────────────────────────────────────────────────────────────────
class TestBookingStatusEnum:
    def test_all_valid_statuses_accepted(self):
        valid = ["Request", "Scheduled", "Ongoing", "Completed", "Cancelled", "No-Show", "Expired"]
        for v in valid:
            assert BookingStatusEnum(v) is not None

    def test_invalid_status_raises_value_error(self):
        with pytest.raises(ValueError):
            BookingStatusEnum("InvalidStatus")

    def test_terminal_states_identified(self):
        terminal = {BookingStatusEnum.COMPLETED, BookingStatusEnum.CANCELLED, BookingStatusEnum.EXPIRED}
        active = {BookingStatusEnum.REQUEST, BookingStatusEnum.SCHEDULED, BookingStatusEnum.ONGOING}
        assert terminal.isdisjoint(active)

    def test_enum_string_values(self):
        assert BookingStatusEnum.REQUEST.value == "Request"
        assert BookingStatusEnum.NO_SHOW.value == "No-Show"
        assert BookingStatusEnum.EXPIRED.value == "Expired"

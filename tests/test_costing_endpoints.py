from datetime import date, datetime, time, timedelta

from app.models.booking import Booking, BookingStatusEnum
from app.models.route_management import RouteManagement, RouteManagementBooking, RouteManagementStatusEnum


def _completed_route(test_db, test_tenant, test_shift, test_vendor, test_vehicle, test_driver, test_employee):
    booking = Booking(
        tenant_id=test_tenant.tenant_id,
        employee_id=test_employee["employee"].employee_id,
        employee_code=test_employee["employee"].employee_code,
        team_id=test_employee["employee"].team_id,
        shift_id=test_shift.shift_id,
        booking_date=date.today(),
        status=BookingStatusEnum.COMPLETED,
        pickup_location="Home",
        drop_location="Office",
        pickup_latitude=12.0,
        pickup_longitude=77.0,
        drop_latitude=12.5,
        drop_longitude=77.5,
    )
    test_db.add(booking)
    test_db.flush()

    route = RouteManagement(
        tenant_id=test_tenant.tenant_id,
        shift_id=test_shift.shift_id,
        route_code="COST-ROUTE-001",
        assigned_vendor_id=test_vendor.vendor_id,
        assigned_vehicle_id=test_vehicle.vehicle_id,
        assigned_driver_id=test_driver.driver_id,
        status=RouteManagementStatusEnum.COMPLETED,
        estimated_total_distance=80.0,
        estimated_total_time=480.0,
        actual_total_distance=92.0,
        actual_start_time=datetime.combine(date.today(), time(9, 0)),
        actual_end_time=datetime.combine(date.today(), time(17, 30)),
    )
    test_db.add(route)
    test_db.flush()
    test_db.add(RouteManagementBooking(route_id=route.route_id, booking_id=booking.booking_id, order_id=1, estimated_distance=80.0))
    test_db.commit()
    test_db.refresh(route)
    return route


def _setup_rate_card(client, employee_token, test_vendor, test_vehicle):
    yesterday = date.today() - timedelta(days=1)
    response = client.post(
        "/api/v1/costing/rate-cards",
        headers={"Authorization": employee_token},
        json={
            "vendor_id": test_vendor.vendor_id,
            "vehicle_type_id": test_vehicle.vehicle_type_id,
            "name": "Sedan Day Rate",
            "effective_from": str(yesterday),
        },
    )
    assert response.status_code == 201, response.text
    rate_card_id = response.json()["data"]["rate_card"]["rate_card_id"]

    response = client.post(
        f"/api/v1/costing/rate-cards/{rate_card_id}/slots",
        headers={"Authorization": employee_token},
        json={
            "name": "Day 8H80KM",
            "shift_log_type": "ANY",
            "day_type": "any",
            "base_amount": 2500,
            "base_km": 80,
            "base_hours": 8,
            "extra_km_rate": 10,
            "extra_hour_rate": 100,
            "tax_percent": 0,
            "priority": 10,
        },
    )
    assert response.status_code == 201, response.text

    response = client.post(
        f"/api/v1/costing/rate-cards/{rate_card_id}/activate",
        headers={"Authorization": employee_token},
    )
    assert response.status_code == 200, response.text


def _setup_vehicle_distance_slab_card(client, employee_token, test_vendor, test_vehicle):
    yesterday = date.today() - timedelta(days=1)
    response = client.post(
        "/api/v1/costing/rate-cards",
        headers={"Authorization": employee_token},
        json={
            "vendor_id": test_vendor.vendor_id,
            "vehicle_type_id": test_vehicle.vehicle_type_id,
            "name": "Sedan Vehicle KM Slab",
            "effective_from": str(yesterday),
        },
    )
    assert response.status_code == 201, response.text
    rate_card_id = response.json()["data"]["rate_card"]["rate_card_id"]

    response = client.post(
        f"/api/v1/costing/rate-cards/{rate_card_id}/slots",
        headers={"Authorization": employee_token},
        json={
            "name": "All Day KM Slabs",
            "shift_log_type": "ANY",
            "day_type": "any",
            "tax_percent": 0,
            "priority": 10,
            "distance_slabs": [
                {"name": "0-15 KM", "min_km": 0, "max_km": 15, "buffer_km": 1, "rate_per_km": 15},
                {"name": "16-30 KM", "min_km": 16, "max_km": 30, "buffer_km": 1, "rate_per_km": 20},
            ],
        },
    )
    assert response.status_code == 201, response.text

    response = client.post(
        f"/api/v1/costing/rate-cards/{rate_card_id}/activate",
        headers={"Authorization": employee_token},
    )
    assert response.status_code == 200, response.text


def test_route_costing_happy_path(client, test_db, employee_token, test_tenant, test_team, test_shift, test_vendor, test_vehicle, test_driver, test_employee):
    route = _completed_route(test_db, test_tenant, test_shift, test_vendor, test_vehicle, test_driver, test_employee)

    response = client.post(
        "/api/v1/cost-centers/",
        headers={"Authorization": employee_token},
        json={"code": "ENG-BLR", "name": "Engineering Bangalore", "is_default": True},
    )
    assert response.status_code == 201, response.text
    cost_center_id = response.json()["data"]["cost_center"]["cost_center_id"]

    response = client.post(
        f"/api/v1/cost-centers/{cost_center_id}/assignments",
        headers={"Authorization": employee_token},
        json={"scope_type": "team", "scope_id": str(test_team.team_id), "effective_from": str(date.today() - timedelta(days=1))},
    )
    assert response.status_code == 201, response.text

    _setup_rate_card(client, employee_token, test_vendor, test_vehicle)

    response = client.post(
        "/api/v1/costing/garage-configs",
        headers={"Authorization": employee_token},
        json={
            "vendor_id": test_vendor.vendor_id,
            "method": "fixed",
            "fixed_start_km": 5,
            "fixed_end_km": 5,
            "fixed_start_hours": 0.25,
            "fixed_end_hours": 0.25,
            "apply_same_km_rate": True,
            "apply_same_hour_rate": True,
        },
    )
    assert response.status_code == 201, response.text

    response = client.post(
        f"/api/v1/routes/{route.route_id}/expenses",
        headers={"Authorization": employee_token},
        json={"expense_type": "toll", "amount": 100, "comment": "Toll"},
    )
    assert response.status_code == 201, response.text
    expense_id = response.json()["data"]["expense"]["expense_id"]

    response = client.post(
        f"/api/v1/routes/{route.route_id}/expenses/{expense_id}/approve",
        headers={"Authorization": employee_token},
    )
    assert response.status_code == 200, response.text

    response = client.post(
        f"/api/v1/routes/{route.route_id}/costing/calculate",
        headers={"Authorization": employee_token},
        json={"distance_source": "actual", "allocation_basis": "headcount"},
    )
    assert response.status_code == 200, response.text
    route_cost = response.json()["data"]["route_cost"]

    assert route_cost["distance_source"] == "actual"
    assert float(route_cost["trip_km"]) == 92.0
    assert float(route_cost["trip_hours"]) == 0.0
    assert float(route_cost["extra_hour_amount"]) == 0.0
    assert float(route_cost["total_amount"]) == 2820.0
    assert route_cost["allocations"][0]["cost_center_code"] == "ENG-BLR"
    assert route_cost["booking_costs"][0]["booking_id"]
    assert route_cost["booking_costs"][0]["cost_center_code"] == "ENG-BLR"
    assert float(route_cost["booking_costs"][0]["route_total_km"]) == 92.0
    assert float(route_cost["booking_costs"][0]["route_total_hours"]) == 0.0
    assert float(route_cost["booking_costs"][0]["allocated_amount"]) == 2820.0

    response = client.get(
        f"/api/v1/routes/{route.route_id}/costing/bookings",
        headers={"Authorization": employee_token},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["booking_costs"][0]["route_total_km"] == 92.0

    response = client.get(
        f"/api/v1/reports/booking-costs?start_date={date.today()}&end_date={date.today()}",
        headers={"Authorization": employee_token},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["booking_costs"][0]["route_total_amount"] == 2820.0


def test_route_costing_uses_vehicle_distance_slab(client, test_db, employee_token, test_tenant, test_shift, test_vendor, test_vehicle, test_driver, test_employee):
    route = _completed_route(test_db, test_tenant, test_shift, test_vendor, test_vehicle, test_driver, test_employee)
    route.estimated_total_distance = 31.0
    route.actual_total_distance = 31.0
    test_db.commit()

    _setup_vehicle_distance_slab_card(client, employee_token, test_vendor, test_vehicle)

    response = client.post(
        f"/api/v1/routes/{route.route_id}/costing/calculate",
        headers={"Authorization": employee_token},
        json={"distance_source": "actual", "allocation_basis": "headcount"},
    )
    assert response.status_code == 200, response.text
    route_cost = response.json()["data"]["route_cost"]

    assert route_cost["calculation_snapshot"]["pricing_mode"] == "distance_slab"
    assert route_cost["calculation_snapshot"]["distance_slab"]["name"] == "16-30 KM"
    assert float(route_cost["trip_km"]) == 31.0
    assert float(route_cost["base_amount"]) == 620.0
    assert float(route_cost["extra_km_amount"]) == 0.0
    assert float(route_cost["total_amount"]) == 620.0
    assert route_cost["line_items"][0]["item_type"] == "KM_SLAB"
    assert float(route_cost["line_items"][0]["rate"]) == 20.0


def test_finalized_route_cost_blocks_recalculation(client, test_db, employee_token, test_tenant, test_shift, test_vendor, test_vehicle, test_driver, test_employee):
    route = _completed_route(test_db, test_tenant, test_shift, test_vendor, test_vehicle, test_driver, test_employee)
    _setup_rate_card(client, employee_token, test_vendor, test_vehicle)

    response = client.post(
        f"/api/v1/routes/{route.route_id}/costing/calculate",
        headers={"Authorization": employee_token},
        json={"distance_source": "actual", "allocation_basis": "headcount"},
    )
    assert response.status_code == 200, response.text

    response = client.post(f"/api/v1/routes/{route.route_id}/costing/submit", headers={"Authorization": employee_token}, json={})
    assert response.status_code == 200, response.text
    response = client.post(f"/api/v1/routes/{route.route_id}/costing/approve", headers={"Authorization": employee_token}, json={})
    assert response.status_code == 200, response.text
    response = client.post(f"/api/v1/routes/{route.route_id}/costing/finalize", headers={"Authorization": employee_token}, json={})
    assert response.status_code == 200, response.text

    response = client.post(
        f"/api/v1/routes/{route.route_id}/costing/calculate",
        headers={"Authorization": employee_token},
        json={"distance_source": "actual", "allocation_basis": "headcount"},
    )
    assert response.status_code == 409

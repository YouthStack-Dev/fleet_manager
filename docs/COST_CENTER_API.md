# Cost Center API Documentation

Base URL: `/api/v1`

All endpoints require Bearer token authentication.

Standard response format:

```json
{
  "success": true,
  "message": "Success message",
  "data": {},
  "timestamp": "2026-06-11 12:00:00"
}
```

Error response format:

```json
{
  "success": false,
  "message": "Error message",
  "error_code": "ERROR_CODE",
  "details": {},
  "timestamp": "2026-06-11 12:00:00"
}
```

## 1. Cost Centers

Cost centers are tenant-level accounting units used to allocate route and booking transport cost.

### 1.1 Create Cost Center

`POST /cost-centers/`

Permission: `cost_center.create`

Request:

```json
{
  "tenant_id": "TEST001",
  "code": "ENG-BLR",
  "name": "Engineering Bangalore",
  "description": "Transport cost for Bangalore engineering team",
  "is_default": false,
  "is_active": true
}
```

Notes:

- `tenant_id` is required for super-admin style tokens without tenant context.
- For employee/admin tokens with tenant context, tenant is resolved from the token.
- `code` is normalized to uppercase.
- Only one default cost center can exist per tenant. Creating/updating a default center clears default from others.

Response:

```json
{
  "success": true,
  "message": "Cost center created successfully",
  "data": {
    "cost_center": {
      "cost_center_id": 1,
      "tenant_id": "TEST001",
      "code": "ENG-BLR",
      "name": "Engineering Bangalore",
      "description": "Transport cost for Bangalore engineering team",
      "is_default": false,
      "is_active": true,
      "created_at": "2026-06-11T10:00:00",
      "updated_at": "2026-06-11T10:00:00"
    }
  }
}
```

### 1.2 List Cost Centers

`GET /cost-centers/`

Permission: `cost_center.read`

Query parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tenant_id` | string | Admin without tenant only | Tenant filter |
| `is_active` | boolean | No | Filter active/inactive centers |

Example:

```bash
GET /api/v1/cost-centers/?is_active=true
```

Response:

```json
{
  "success": true,
  "message": "Cost centers fetched successfully",
  "data": {
    "cost_centers": [
      {
        "cost_center_id": 1,
        "tenant_id": "TEST001",
        "code": "ENG-BLR",
        "name": "Engineering Bangalore",
        "is_default": false,
        "is_active": true
      }
    ],
    "total": 1
  }
}
```

### 1.3 Get Cost Center Detail

`GET /cost-centers/{cost_center_id}`

Permission: `cost_center.read`

Query parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tenant_id` | string | Admin without tenant only | Tenant context |

Example:

```bash
GET /api/v1/cost-centers/1
```

### 1.4 Update Cost Center

`PATCH /cost-centers/{cost_center_id}`

Permission: `cost_center.update`

Request:

```json
{
  "code": "ENG-BLR",
  "name": "Engineering Bangalore Updated",
  "description": "Updated description",
  "is_default": true,
  "is_active": true
}
```

All fields are optional.

### 1.5 Deactivate Cost Center

`DELETE /cost-centers/{cost_center_id}`

Permission: `cost_center.delete`

Behavior:

- Soft-deactivates the cost center by setting `is_active=false`.
- Historical route/booking cost rows remain unchanged.

Response:

```json
{
  "success": true,
  "message": "Cost center deactivated successfully",
  "data": null
}
```

## 2. Cost Center Assignments

Assignments define which cost center applies to a tenant, team, or employee.

Resolution priority:

1. Booking snapshot `bookings.cost_center_id`, if already set.
2. Employee assignment.
3. Team assignment.
4. Tenant assignment.
5. Tenant default cost center.
6. System-created `UNALLOCATED` cost center.

### 2.1 Create Assignment

`POST /cost-centers/{cost_center_id}/assignments`

Permission: `cost_center.update`

Request:

```json
{
  "scope_type": "team",
  "scope_id": "10",
  "effective_from": "2026-06-01",
  "effective_to": null,
  "is_active": true
}
```

Allowed `scope_type` values:

| Value | `scope_id` |
|-------|------------|
| `employee` | Employee ID |
| `team` | Team ID |
| `tenant` | Tenant ID |

Validation:

- Scope must exist in the same tenant.
- Active assignment date ranges cannot overlap for the same scope.

Response:

```json
{
  "success": true,
  "message": "Cost center assignment created successfully",
  "data": {
    "assignment": {
      "assignment_id": 1,
      "tenant_id": "TEST001",
      "cost_center_id": 1,
      "scope_type": "team",
      "scope_id": "10",
      "effective_from": "2026-06-01",
      "effective_to": null,
      "is_active": true
    }
  }
}
```

### 2.2 Resolve Cost Center

`GET /cost-centers/resolve`

Permission: `cost_center.read`

Query parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `booking_id` | int | One of booking/employee | Resolve using booking |
| `employee_id` | int | One of booking/employee | Resolve using employee/team |
| `as_of` | date | No | Assignment effective date, default today |
| `tenant_id` | string | Admin without tenant only | Tenant context |

Examples:

```bash
GET /api/v1/cost-centers/resolve?booking_id=501
GET /api/v1/cost-centers/resolve?employee_id=100&as_of=2026-06-11
```

Response:

```json
{
  "success": true,
  "message": "Cost center resolved successfully",
  "data": {
    "cost_center": {
      "cost_center_id": 1,
      "code": "ENG-BLR",
      "name": "Engineering Bangalore"
    }
  }
}
```

## 3. Rate Cards

Rate cards define vendor/vehicle commercial pricing.

### 3.1 Create Rate Card

`POST /costing/rate-cards`

Permission: `costing_rate_card.create`

Request:

```json
{
  "tenant_id": "TEST001",
  "vendor_id": 1,
  "vehicle_type_id": 1,
  "name": "Sedan Day Rate",
  "currency": "INR",
  "effective_from": "2026-06-01",
  "effective_to": null,
  "status": "draft"
}
```

Notes:

- `vendor_id=null` means tenant default card.
- `vehicle_type_id=null` means any vehicle type.
- Activate only after adding at least one slot.

### 3.2 List Rate Cards

`GET /costing/rate-cards`

Permission: `costing_rate_card.read`

Query parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tenant_id` | string | Admin without tenant only | Tenant context |
| `vendor_id` | int | No | Vendor filter |
| `status` | string | No | `draft`, `active`, `expired`, `archived` |

### 3.3 Update Rate Card

`PATCH /costing/rate-cards/{rate_card_id}`

Permission: `costing_rate_card.update`

All request fields from create are optional.

### 3.4 Activate Rate Card

`POST /costing/rate-cards/{rate_card_id}/activate`

Permission: `costing_rate_card.approve`

Validation:

- Rate card must exist in tenant.
- Rate card must have at least one slot.

## 4. Rate Card Slots

Slots define time/day windows inside a rate card. Each slot operates in one of two pricing modes:

- **Legacy base-package mode**: no distance slabs on the slot; bills `base_amount` + `extra_km_rate × extra_km`.
- **Distance slab mode**: slot has one or more active `distance_slabs`; bills `trip_km × matched_slab.rate_per_km` with no separate base or extra-KM charge.

### 4.1 Create Slot

`POST /costing/rate-cards/{rate_card_id}/slots`

Permission: `costing_rate_card.update`

**Legacy base-package example:**

```json
{
  "name": "Day 80KM",
  "shift_log_type": "ANY",
  "day_type": "any",
  "start_time": "06:00:00",
  "end_time": "21:59:59",
  "base_amount": 2500,
  "base_km": 80,
  "extra_km_rate": 10,
  "waiting_rate_per_hour": 0,
  "escort_rate": 0,
  "night_allowance": 0,
  "tax_percent": 0,
  "priority": 10,
  "is_active": true,
  "distance_slabs": []
}
```

**Distance slab example:**

```json
{
  "name": "Sedan KM Slab",
  "shift_log_type": "ANY",
  "day_type": "any",
  "base_amount": 0,
  "base_km": 0,
  "extra_km_rate": 0,
  "escort_rate": 0,
  "night_allowance": 0,
  "tax_percent": 0,
  "priority": 10,
  "is_active": true,
  "distance_slabs": [
    { "name": "0-15 KM",  "min_km": 0,  "max_km": 15, "buffer_km": 1, "rate_per_km": 25, "is_active": true },
    { "name": "16-30 KM", "min_km": 16, "max_km": 30, "buffer_km": 1, "rate_per_km": 20, "is_active": true },
    { "name": "31-50 KM", "min_km": 31, "max_km": 50, "buffer_km": 2, "rate_per_km": 15, "is_active": true }
  ]
}
```

Allowed values:

| Field | Values |
|-------|--------|
| `shift_log_type` | `ANY`, `IN`, `OUT` |
| `day_type` | `any`, `weekday`, `weekend`, `holiday` |

Validation:

- Active slots with same `shift_log_type` and `day_type` cannot overlap in time for the same rate card.
- Overnight windows are supported, for example `22:00:00` to `05:59:59`.
- `distance_slabs` defaults to `[]` (empty = legacy mode).

### 4.2 Update Slot

`PATCH /costing/rate-cards/{rate_card_id}/slots/{slot_id}`

Permission: `costing_rate_card.update`

All slot fields are optional. When `distance_slabs` is included in the request body, all existing slabs for the slot are deleted and replaced with the supplied list. Omitting `distance_slabs` entirely leaves existing slabs unchanged.

### 4.3 Distance Slabs (Slab Pricing Mode)

Distance slabs are nested inside a slot and activate bracket-based per-KM pricing.

**Slab selection rule:**

A slab matches if `slab.min_km ≤ trip_km ≤ (slab.max_km + slab.buffer_km)`. The first matching active slab is used; if no slab matches, the slot is skipped during rate resolution.

**Billing formula (slab mode):**

```text
base_amount    = trip_km × matched_slab.rate_per_km
extra_km_amount = 0
```

The `buffer_km` extends the upper boundary of a slab to cover small overruns. For example, a slab with `max_km=30, buffer_km=1` covers trips up to 31 km.

`RateCardDistanceSlab` response fields:

| Field | Type | Description |
|-------|------|-------------|
| `distance_slab_id` | int | Primary key |
| `slot_id` | int | Parent slot |
| `name` | string | Display label, e.g. `"16-30 KM"` |
| `min_km` | decimal | Lower boundary (inclusive) |
| `max_km` | decimal | Upper boundary before buffer |
| `buffer_km` | decimal | Added to `max_km` for matching |
| `rate_per_km` | decimal | Per-KM charge for this bracket |
| `is_active` | bool | Only active slabs are used for matching |
| `created_at`, `updated_at` | datetime | Audit fields |

## 5. Garage Config

Garage config controls garage KM additions.

Initial implementation supports:

- `none`
- `fixed`

### 5.1 Create Garage Config

`POST /costing/garage-configs`

Permission: `costing_rate_card.update`

Request:

```json
{
  "tenant_id": "TEST001",
  "vendor_id": 1,
  "vehicle_id": null,
  "method": "fixed",
  "fixed_start_km": 5,
  "fixed_end_km": 5,
  "apply_same_km_rate": true,
  "is_active": true
}
```

Garage cost formula:

```text
garage_km = fixed_start_km + fixed_end_km
garage_amount = garage_km * extra_km_rate
```

Hours are not billed in the current implementation. Any hour-related garage fields are ignored for costing.

### 5.2 List Garage Configs

`GET /costing/garage-configs`

Permission: `costing_rate_card.read`

Query parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tenant_id` | string | Admin without tenant only | Tenant context |
| `vendor_id` | int | No | Vendor filter |

### 5.3 Update Garage Config

`PATCH /costing/garage-configs/{garage_config_id}`

Permission: `costing_rate_card.update`

## 6. Route Costing

Route costing calculates the completed route total first, then creates per-booking cost rows.

Route-level behavior:

- Uses route total KM for slab calculation.
- Uses `actual_total_distance` when available and requested.
- Falls back to `estimated_total_distance` when actual KM is unavailable.
- Includes fixed garage cost and approved expenses.
- Does not calculate or bill hours. Hour fields in responses are returned as `0` for compatibility.

Booking-level behavior:

- Each booking row stores the route total KM used for the slab.
- Each booking row stores booking planned/actual KM when available.
- Initial allocation is equal headcount split.

### 6.1 Calculate Route Cost

`POST /routes/{route_id}/costing/calculate`

Permission: `route_cost.calculate`

Request:

```json
{
  "dry_run": false,
  "distance_source": "actual",
  "allocation_basis": "headcount",
  "manual_trip_km": null,
  "comment": "June billing run"
}
```

Allowed `distance_source` values:

| Value | Behavior |
|-------|----------|
| `actual` | Use route actual KM, fallback to planned KM |
| `planned` | Use route planned KM |
| `manual` | Use `manual_trip_km`; hours are ignored |
| `reference` | Reserved, not implemented yet |

Response includes route totals, line items, cost-center allocations, and booking costs.

**Legacy base-package response example** (slot without distance slabs):

```json
{
  "success": true,
  "message": "Route cost calculated successfully",
  "data": {
    "route_cost": {
      "route_cost_id": 1,
      "route_id": 1000,
      "status": "draft",
      "distance_source": "actual",
      "trip_km": 92,
      "trip_hours": 0,
      "garage_km": 10,
      "base_amount": 2500,
      "extra_km_amount": 120,
      "extra_hour_amount": 0,
      "garage_amount": 100,
      "expense_amount": 100,
      "tax_amount": 0,
      "total_amount": 2820,
      "line_items": [
        { "item_type": "BASE_PACKAGE", "amount": 2500 },
        { "item_type": "EXTRA_KM", "quantity": 12, "rate": 10, "amount": 120 },
        { "item_type": "GARAGE", "quantity": 10, "amount": 100 },
        { "item_type": "EXPENSES", "amount": 100 }
      ],
      "allocations": [
        {
          "cost_center_code": "ENG-BLR",
          "basis": "headcount",
          "booking_count": 2,
          "allocation_percent": 100,
          "allocated_amount": 2820
        }
      ],
      "booking_costs": [
        {
          "booking_id": 501,
          "cost_center_code": "ENG-BLR",
          "distance_source": "actual",
          "route_total_km": 92,
          "route_total_hours": 0,
          "booking_planned_km": 20,
          "booking_actual_km": 21,
          "allocation_percent": 50,
          "allocated_amount": 1410
        }
      ]
    }
  }
}
```

**Distance slab response example** (slot with matching slab `16-30 KM` at `₹20/km`, `trip_km=31`):

```json
{
  "success": true,
  "message": "Route cost calculated successfully",
  "data": {
    "route_cost": {
      "route_cost_id": 2,
      "route_id": 1001,
      "status": "draft",
      "distance_source": "actual",
      "trip_km": 31,
      "trip_hours": 0,
      "garage_km": 0,
      "base_amount": 620,
      "extra_km_amount": 0,
      "extra_hour_amount": 0,
      "garage_amount": 0,
      "expense_amount": 0,
      "tax_amount": 0,
      "total_amount": 620,
      "line_items": [
        {
          "item_type": "KM_SLAB",
          "description": "16-30 KM @ ₹20/km",
          "quantity": 31,
          "rate": 20,
          "amount": 620
        }
      ],
      "allocations": [
        {
          "cost_center_code": "ENG-BLR",
          "basis": "headcount",
          "booking_count": 1,
          "allocation_percent": 100,
          "allocated_amount": 620
        }
      ],
      "booking_costs": []
    }
  }
}
```

Notes on rate resolution:

- The system tests vehicle-specific active rate cards first, then vendor+vehicle-type cards, then vendor-only cards, then tenant default.
- A slot that has active distance slabs requires a matching slab for `trip_km`; if none matches the slot is skipped and the next lower-priority slot is tried.
- `item_type` is `KM_SLAB` in slab mode and `BASE_PACKAGE` in legacy mode.

### 6.2 Get Route Cost

`GET /routes/{route_id}/costing`

Permission: `route_cost.read`

Returns the saved route cost, line items, cost-center allocations, and booking costs.

### 6.3 Get Route Booking Costs

`GET /routes/{route_id}/costing/bookings`

Permission: `route_cost.read`

Returns only the per-booking cost rows.

Example response:

```json
{
  "success": true,
  "message": "Route booking costs fetched successfully",
  "data": {
    "booking_costs": [
      {
        "route_booking_cost_id": 1,
        "route_cost_id": 1,
        "route_id": 1000,
        "booking_id": 501,
        "cost_center_code": "ENG-BLR",
        "route_total_km": 92,
        "booking_planned_km": 20,
        "booking_actual_km": 21,
        "allocation_percent": 50,
        "allocated_amount": 1410
      }
    ],
    "total": 1
  }
}
```

### 6.4 Submit Route Cost

`POST /routes/{route_id}/costing/submit`

Permission: `route_cost.submit`

Request:

```json
{ "comment": "Submitted for approval" }
```

Allowed from statuses:

- `draft`
- `rejected`

### 6.5 Approve Route Cost

`POST /routes/{route_id}/costing/approve`

Permission: `route_cost.approve`

Allowed from statuses:

- `draft`
- `submitted`

### 6.6 Reject Route Cost

`POST /routes/{route_id}/costing/reject`

Permission: `route_cost.approve`

Request:

```json
{ "comment": "Actual KM variance needs review" }
```

### 6.7 Finalize Route Cost

`POST /routes/{route_id}/costing/finalize`

Permission: `route_cost.finalize`

Allowed from status:

- `approved`

Behavior:

- Locks route cost.
- Recalculation is blocked after finalization.

## 7. Route Expenses

Approved expenses are added to route cost during calculation.

### 7.1 Create Expense

`POST /routes/{route_id}/expenses`

Permission: `route_expense.create`

Request:

```json
{
  "expense_type": "toll",
  "amount": 100,
  "comment": "Airport toll",
  "attachment_url": "https://example.com/toll.jpg"
}
```

Allowed expense types:

- `toll`
- `parking`
- `permit`
- `fuel`
- `driver_bata`
- `other`

### 7.2 List Expenses

`GET /routes/{route_id}/expenses`

Permission: `route_expense.read`

### 7.3 Update Draft Expense

`PATCH /routes/{route_id}/expenses/{expense_id}`

Permission: `route_expense.update`

Only `draft` expenses can be edited.

### 7.4 Submit Expenses

`POST /routes/{route_id}/expenses/submit`

Permission: `route_expense.submit`

Changes all route `draft` expenses to `pending_approval`.

### 7.5 Approve Expense

`POST /routes/{route_id}/expenses/{expense_id}/approve`

Permission: `route_expense.approve`

### 7.6 Reject Expense

`POST /routes/{route_id}/expenses/{expense_id}/reject`

Permission: `route_expense.approve`

Request:

```json
{ "reason": "Receipt not clear" }
```

## 8. Reports

### 8.1 Route Cost Report

`GET /reports/route-costs`

Permission: `route_cost.report.read`

Query parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | date | Yes | Start date |
| `end_date` | date | Yes | End date |
| `tenant_id` | string | Admin without tenant only | Tenant context |
| `vendor_id` | int | No | Vendor filter |
| `cost_status` | string | No | `draft`, `submitted`, `approved`, `rejected`, `finalized` |
| `cost_center_id` | int | No | Cost center filter |

### 8.2 Booking Cost Report

`GET /reports/booking-costs`

Permission: `route_cost.report.read`

Query parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | date | Yes | Start date |
| `end_date` | date | Yes | End date |
| `tenant_id` | string | Admin without tenant only | Tenant context |
| `route_id` | int | No | Route filter |
| `booking_id` | int | No | Booking filter |
| `cost_center_id` | int | No | Cost center filter |

Response fields include:

- `route_id`
- `route_code`
- `booking_id`
- `employee_id`
- `employee_code`
- `cost_center_code`
- `route_total_km`
- `booking_planned_km`
- `booking_actual_km`
- `allocation_percent`
- `allocated_amount`
- `route_total_amount`

### 8.3 Route Cost Excel Export

`GET /reports/route-costs/export`

Permission: `route_cost.report.read`

Query parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | date | Yes | Start date |
| `end_date` | date | Yes | End date |
| `tenant_id` | string | Admin without tenant only | Tenant context |

Response:

- Excel file download.

### 8.4 Cost Center Summary

`GET /reports/cost-centers/summary`

Permission: `route_cost.report.read`

Query parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | date | Yes | Start date |
| `end_date` | date | Yes | End date |
| `tenant_id` | string | Admin without tenant only | Tenant context |

## 9. Common Flow

1. Create cost center.
2. Assign cost center to tenant/team/employee.
3. Create rate card.
4. Add one or more slots.
5. Activate rate card.
6. Configure garage, if applicable.
7. Complete route.
8. Add and approve expenses, if any.
9. Calculate route cost.
10. Review `booking_costs` under route cost.
11. Submit, approve, and finalize route cost.

## 10. Error Codes

| Error Code | Meaning |
|------------|---------|
| `TENANT_ID_REQUIRED` | Tenant context missing |
| `COST_CENTER_NOT_FOUND` | Cost center does not exist in tenant |
| `ASSIGNMENT_OVERLAP` | Assignment date range overlaps existing active assignment |
| `SCOPE_NOT_FOUND` | Team/employee/tenant scope not found |
| `RATE_CARD_NOT_FOUND` | Rate card not found |
| `RATE_CARD_HAS_NO_SLOTS` | Cannot activate card without slots |
| `RATE_SLOT_OVERLAP` | Active rate slot overlaps another active slot |
| `RATE_SLOT_NOT_FOUND` | No matching active slot found for route (also raised when all slab-mode slots exist but none has a distance slab covering `trip_km`) |
| `GARAGE_CONFIG_NOT_FOUND` | Garage config not found |
| `GARAGE_METHOD_NOT_SUPPORTED` | Non-fixed garage method requested in initial release |
| `ROUTE_NOT_FOUND` | Route not found in tenant |
| `ROUTE_NOT_COMPLETED` | Route must be completed for final costing |
| `ROUTE_COST_NOT_FOUND` | Route cost has not been calculated |
| `ROUTE_COST_FINALIZED` | Finalized route cost is locked |
| `EXPENSE_NOT_FOUND` | Expense not found |
| `EXPENSE_NOT_EDITABLE` | Expense is not in draft status |
| `INVALID_EXPENSE_STATUS` | Expense approval transition not allowed |

# Contract Costing API Usage Guide

This guide explains how to use the Contract + Slab-Based Costing APIs.

Base URL:

```text
{{base_url}}/api/v1
```

Example local value:

```text
http://localhost:8000/api/v1
```

All APIs require bearer auth:

```http
Authorization: Bearer {{token}}
```

Required permissions:

| API Group | Permission |
|-----------|------------|
| Create contract | `contract.create` |
| Read/list/calculate | `contract.read` |
| Update contract/slabs | `contract.update` |
| Delete contract | `contract.delete` |
| Assign contract to vehicle | `vehicle.update` |

---

## Important Concepts

### Contract

A Contract is the pricing agreement for a vendor and a vehicle type.

```text
Vendor + Vehicle Type = Contract
```

Example:

```text
Vendor: ABC Travels
Vehicle Type: SEDAN
Contract: Sedan City Contract
```

Rules:

- `contract_name` is unique per vendor.
- One active/inactive contract is allowed per `vendor_id + vehicle_type_id` pair.
- `cost_center_id` is currently a nullable placeholder for the future employee-side cost center module. It is not validated as a foreign key yet.

### Contract Slab

A slab defines per-kilometer pricing for a distance range.

Example:

```text
0 km to 10 km  -> 10 per km
10 km to 20 km -> 15 per km
20 km onwards  -> 20 per km
```

Rules:

- First active slab must start at `0`.
- Slabs must be continuous with no gaps.
- `max_km = null` means final unlimited slab.
- `rate` must be greater than `0`.
- `max_km` must be greater than `min_km` when provided.

### Vehicle Contract Assignment

Vehicles can be assigned a contract with `contract_id`.

Rules:

- `contract_id` is required when creating a new vehicle.
- Vehicle contract must belong to the same vendor.
- Vehicle contract must match the vehicle's `vehicle_type_id`.
- Passing `contract_id=0` in vehicle update clears the contract.

---

## Recommended Setup Flow

### Step 1: Create Contract

Create one contract for a vendor and vehicle type.

```http
POST /api/v1/contracts
Content-Type: application/json
```

Admin/employee users must send `vendor_id`.

Vendor users can omit `vendor_id`; the vendor is taken from token.

Request:

```json
{
  "vendor_id": 1,
  "vehicle_type_id": 2,
  "contract_name": "Sedan City Contract",
  "cost_center_id": null,
  "is_active": true
}
```

Response:

```json
{
  "success": true,
  "message": "Contract created successfully",
  "data": {
    "contract": {
      "contract_id": 1,
      "vendor_id": 1,
      "vehicle_type_id": 2,
      "vehicle_type_name": "SEDAN",
      "contract_name": "Sedan City Contract",
      "cost_center_id": null,
      "is_active": true,
      "slabs": [],
      "created_at": "2026-06-11T18:00:00",
      "updated_at": "2026-06-11T18:00:00"
    }
  },
  "timestamp": "2026-06-11 18:00:00"
}
```

---

### Step 2: Add First Slab

```http
POST /api/v1/contracts/{contract_id}/slabs
Content-Type: application/json
```

Request:

```json
{
  "min_km": 0,
  "max_km": 10,
  "rate": 10,
  "is_active": true
}
```

Response:

```json
{
  "success": true,
  "message": "Contract slab created successfully",
  "data": {
    "slab": {
      "slab_id": 1,
      "contract_id": 1,
      "min_km": 0,
      "max_km": 10,
      "rate": 10,
      "is_active": true
    }
  }
}
```

---

### Step 3: Add Next Slab

The next slab must start exactly where the previous slab ended.

```http
POST /api/v1/contracts/{contract_id}/slabs
Content-Type: application/json
```

Request:

```json
{
  "min_km": 10,
  "max_km": 20,
  "rate": 15,
  "is_active": true
}
```

---

### Step 4: Add Final Open-Ended Slab

Use `max_km: null` for all distance above 20 km.

```http
POST /api/v1/contracts/{contract_id}/slabs
Content-Type: application/json
```

Request:

```json
{
  "min_km": 20,
  "max_km": null,
  "rate": 20,
  "is_active": true
}
```

---

### Step 5: Assign Contract to Vehicle

When creating a new vehicle, `contract_id` is mandatory in the existing multipart vehicle create API.

```http
POST /api/v1/vehicles
Content-Type: multipart/form-data
```

Required contract field:

| Key | Value |
|-----|-------|
| `contract_id` | `1` |

For existing vehicles, use the vehicle update API.

Existing vehicle update API accepts `contract_id` as form-data.

```http
PUT /api/v1/vehicles/{vehicle_id}
Content-Type: multipart/form-data
```

Form-data:

| Key | Value |
|-----|-------|
| `contract_id` | `1` |

Response includes:

```json
{
  "success": true,
  "message": "Vehicle updated successfully",
  "data": {
    "vehicle": {
      "vehicle_id": 15,
      "vehicle_type_id": 2,
      "contract_id": 1,
      "contract_name": "Sedan City Contract",
      "vendor_id": 1
    }
  }
}
```

To clear a vehicle contract:

```text
contract_id=0
```

---

### Step 5.1: List Vendor Vehicles With Contract Details

Use this for UI dropdowns/tables after selecting a vendor.

```http
GET /api/v1/contracts/vendor/{vendor_id}/contract-summary
```

Example:

```http
GET /api/v1/contracts/vendor/1/contract-summary?active_only=true
```

Response:

```json
{
  "success": true,
  "message": "Vehicle contract summary fetched successfully",
  "data": {
    "vendor_id": 1,
    "total": 2,
    "items": [
      {
        "vehicle_id": 15,
        "vehicle_label": "SEDAN - KA05MX1234",
        "rc_number": "KA05MX1234",
        "vehicle_type_id": 2,
        "vehicle_type_name": "SEDAN",
        "contract_id": 1,
        "contract_name": "Sedan City Contract",
        "driver_id": 10,
        "driver_name": "Ravi Driver",
        "is_active": true
      }
    ]
  }
}
```

---

### Step 6: Complete Route

Route completion is handled by the existing driver duty flow. Once the route is completed:

- `RouteManagement.status` must be `Completed`.
- `RouteManagement.actual_total_distance` must be set.
- `RouteManagement.assigned_vehicle_id` must point to a vehicle with `contract_id`.

---

### Step 7: Calculate Completed Route Cost

```http
POST /api/v1/contracts/calculate/{route_id}
```

Example:

```http
POST /api/v1/contracts/calculate/42
```

Response for 18 km with slabs `0-10 @ 10` and `10-20 @ 15`:

```json
{
  "success": true,
  "message": "Route cost calculated successfully",
  "data": {
    "route_id": 42,
    "contract_id": 1,
    "contract_name": "Sedan City Contract",
    "vehicle_id": 15,
    "vehicle_type_name": "SEDAN",
    "vendor_id": 1,
    "total_distance_km": 18,
    "total_cost": 220,
    "effective_rate": 12.22,
    "slab_breakdown": [
      {
        "min_km": 0,
        "max_km": 10,
        "km_used": 10,
        "rate": 10,
        "cost": 100
      },
      {
        "min_km": 10,
        "max_km": 20,
        "km_used": 8,
        "rate": 15,
        "cost": 120
      }
    ]
  }
}
```

---

## Endpoint Reference

### Create Contract

```http
POST /api/v1/contracts
```

Body:

```json
{
  "vendor_id": 1,
  "vehicle_type_id": 2,
  "contract_name": "Sedan City Contract",
  "cost_center_id": null,
  "is_active": true
}
```

Notes:

- Admin/employee: `vendor_id` required.
- Vendor: `vendor_id` ignored/taken from token.

---

### List Contracts

```http
GET /api/v1/contracts?vendor_id=1&active_only=true&vehicle_type_id=2&search=Sedan
```

Query params:

| Name | Required | Description |
|------|----------|-------------|
| `vendor_id` | Admin/employee yes, vendor no | Vendor filter |
| `vehicle_type_id` | No | Filter by vehicle type |
| `active_only` | No | `true` or `false` |
| `search` | No | Search by contract name |

---

### Get Contract

```http
GET /api/v1/contracts/{contract_id}
```

Returns contract with slabs.

---

### Update Contract

```http
PUT /api/v1/contracts/{contract_id}
```

Body:

```json
{
  "contract_name": "Updated Sedan Contract",
  "cost_center_id": null,
  "is_active": true
}
```

Notes:

- `vehicle_type_id` can be changed only when no vehicles are assigned to the contract.

---

### Toggle Contract Status

```http
PATCH /api/v1/contracts/{contract_id}/toggle-status
```

Toggles `is_active` from true to false or false to true.

---

### Delete Contract

```http
DELETE /api/v1/contracts/{contract_id}?force=false
```

This is a soft delete. It sets `is_active=false`.

If vehicles are assigned:

- `force=false` blocks delete.
- `force=true` clears `contract_id` from assigned vehicles, then deactivates the contract.

---

### Add Slab

```http
POST /api/v1/contracts/{contract_id}/slabs
```

Body:

```json
{
  "min_km": 0,
  "max_km": 10,
  "rate": 10,
  "is_active": true
}
```

---

### Update Slab

```http
PUT /api/v1/contracts/{contract_id}/slabs/{slab_id}
```

Body:

```json
{
  "min_km": 10,
  "max_km": 20,
  "rate": 15,
  "is_active": true
}
```

---

### Delete Slab

```http
DELETE /api/v1/contracts/{contract_id}/slabs/{slab_id}
```

Notes:

- Deleting a slab can break contiguity.
- If active slabs remain, they must still be contiguous.
- Empty slab list is allowed after deletion.

---

### Calculate Route Cost

```http
POST /api/v1/contracts/calculate/{route_id}
```

Requires:

- Route status is `Completed`.
- Route has `actual_total_distance > 0`.
- Route has an assigned vehicle.
- Vehicle has an active matching contract.
- Contract has active slabs covering the full route distance.

---

### List Vendor Vehicle Contract Summary

```http
GET /api/v1/contracts/vendor/{vendor_id}/contract-summary?active_only=true
```

Returns lightweight vehicle assignment data:

```json
{
  "vehicle_id": 15,
  "vehicle_label": "SEDAN - KA05MX1234",
  "rc_number": "KA05MX1234",
  "vehicle_type_id": 2,
  "vehicle_type_name": "SEDAN",
  "contract_id": 1,
  "contract_name": "Sedan City Contract",
  "driver_id": 10,
  "driver_name": "Ravi Driver",
  "is_active": true
}
```

---

## Common Errors

| Error Code | Meaning | Fix |
|------------|---------|-----|
| `VENDOR_ID_REQUIRED` | Admin/employee did not pass vendor_id | Pass `vendor_id` |
| `INVALID_VEHICLE_TYPE` | Vehicle type does not belong to vendor | Use vendor's vehicle type |
| `CONTRACT_NAME_CONFLICT` | Duplicate contract name for vendor | Use a different name |
| `CONTRACT_VEHICLE_TYPE_CONFLICT` | Contract already exists for vendor+vehicle type | Use existing contract |
| `INVALID_SLAB_CHAIN` | Slabs have gap/overlap or do not start at 0 | Fix min/max ranges |
| `VEHICLE_CONTRACT_REQUIRED` | Vehicle has no contract | Assign contract to vehicle |
| `ROUTE_NOT_COMPLETED` | Route status is not completed | Complete route first |
| `ROUTE_DISTANCE_REQUIRED` | Route has no actual distance | Ensure distance calculation is persisted |
| `DISTANCE_NOT_COVERED_BY_SLABS` | Route distance exceeds slabs | Add open-ended final slab |

---

## Postman Collection

Import this file into Postman:

```text
docs/CONTRACT_COSTING_POSTMAN_COLLECTION.json
```

Set collection variables:

| Variable | Example |
|----------|---------|
| `base_url` | `http://localhost:8000` |
| `token` | JWT access token |
| `vendor_id` | `1` |
| `vehicle_type_id` | `2` |
| `contract_id` | auto-filled after create |
| `slab_id` | auto-filled after slab create |
| `vehicle_id` | existing vehicle id |
| `route_id` | completed route id |

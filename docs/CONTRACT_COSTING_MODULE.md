# Contract & Slab-Based Costing Module

## Overview

This module enables cost calculation for completed routes based on **Contracts** negotiated per vendor and vehicle type. Each contract contains **distance-based slabs** (e.g. 0–10km @ ₹10/km, 10–20km @ ₹15/km) and vehicles are assigned a contract. When a route completes, the system looks up the vehicle's contract, finds the matching slabs, and progressively calculates the total cost.

**Core entities:**
- **Contract** — links a Vendor + Vehicle Type together with a pricing agreement
- **ContractSlab** — per-km rate for a distance range within a contract
- **Vehicle.contract_id** — required during new vehicle creation; controls which contract applies to this vehicle

---

## Data Model

### `contracts` table

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| `contract_id` | Integer, PK | auto-increment | |
| `vendor_id` | Integer, FK → vendors | NOT NULL | Owning vendor |
| `vehicle_type_id` | Integer, FK → vehicle_types | NOT NULL | Vehicle type this contract covers |
| `cost_center_id` | Integer | NULLABLE | Placeholder reference for future employee-side cost center module |
| `contract_name` | String(150) | NOT NULL | Human-readable name |
| `is_active` | Boolean | DEFAULT TRUE | Soft delete / disable |
| `created_at` | DateTime | func.now() | |
| `updated_at` | DateTime | func.now(), onupdate | |

**Unique constraints:**
1. `(vendor_id, contract_name)` — no duplicate contract names within a vendor
2. `(vendor_id, vehicle_type_id)` — only one contract per vendor+vehicle_type pair

### `contract_slabs` table

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| `slab_id` | Integer, PK | auto-increment | |
| `contract_id` | Integer, FK → contracts | NOT NULL, CASCADE delete | Parent contract |
| `min_km` | Float | NOT NULL, >= 0 | Inclusive lower bound |
| `max_km` | Float | NULLABLE | Exclusive upper bound (NULL = infinity for last slab) |
| `rate` | Float | NOT NULL, > 0 | ₹ per km for this slab |
| `is_active` | Boolean | DEFAULT TRUE | |
| `created_at` | DateTime | func.now() | |
| `updated_at` | DateTime | func.now(), onupdate | |

**Unique constraints:**
1. `(contract_id, min_km)` — no two slabs in the same contract start at the same km

**Validation rules:**
- `min_km >= 0`, `rate > 0`
- If `max_km` is provided: `max_km > min_km`
- Slabs within a contract must be contiguous (no gaps). E.g. 0–10, 10–20 is valid; 0–5, 10–15 is invalid.

### `vehicles` — added column

| Column | Type | Constraints | Description |
|--------|------|------------|-------------|
| `contract_id` | Integer, FK → contracts | NULLABLE | Contract assigned to this vehicle |

Note: the column is nullable to support existing vehicles and migration safety, but the vehicle create API requires `contract_id` for new vehicles.

---

## File Structure

```
app/
├── models/
│   ├── contract.py              # NEW — Contract, ContractSlab ORM models
│   ├── vehicle.py               # EDIT — add contract_id column
│   └── __init__.py              # EDIT — import new models
├── schemas/
│   ├── contract.py              # NEW — all Pydantic schemas
│   └── vehicle.py               # EDIT — add contract_id to schemas
├── crud/
│   ├── contract.py              # NEW — CRUDContract, CRUDContractSlab
│   └── vehicle.py               # EDIT — handle contract_id in create/update
├── routes/
│   ├── contract_router.py       # NEW — all endpoints
│   └── __init__.py              # EDIT — export contract_router
├── services/
│   └── contract_service.py      # NEW — cost calculation business logic
└── api.py                       # EDIT — register contract_router
migrations/versions/
└── 20260611_1300_add_contract_tables.py  # NEW

docs/
└── CONTRACT_COSTING_MODULE.md   # THIS FILE
```

---

## Pydantic Schemas (`app/schemas/contract.py`)

### Slab Schemas

```
SlabBase     →  min_km, max_km (optional), rate
SlabCreate   ── extends SlabBase
SlabUpdate   ── all optional: min_km, max_km, rate, is_active
SlabResponse ── slab_id, contract_id, is_active, created_at, updated_at
```

### Contract Schemas

```
ContractBase       →  contract_name, vehicle_type_id, cost_center_id (optional)
ContractCreate     ── extends ContractBase + vendor_id (optional, resolved from token)
ContractUpdate     ── all optional: contract_name, vehicle_type_id, cost_center_id, is_active
ContractResponse   ── contract_id, vendor_id, is_active, slabs[], created_at, updated_at
```

### Cost Calculation Schemas

```
CostSlabBreakdown  →  min_km, max_km, km_used, rate, cost
CostCalcResponse   →  route_id, contract_id, contract_name, vehicle_id,
                      vehicle_type_name, vendor_id, total_distance_km,
                      total_cost, effective_rate, slab_breakdown[]
```

---

## API Endpoints

All under `/api/v1/contracts`.

### Contract CRUD

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| POST | `/contracts` | `contract.create` | Create a new contract |
| GET | `/contracts` | `contract.read` | List contracts (filter by vendor, vehicle_type, active) |
| GET | `/contracts/{contract_id}` | `contract.read` | Get single contract with slabs |
| PUT | `/contracts/{contract_id}` | `contract.update` | Update contract details |
| PATCH | `/contracts/{contract_id}/toggle-status` | `contract.update` | Activate / deactivate |
| DELETE | `/contracts/{contract_id}` | `contract.delete` | Soft delete (set inactive) |

### Slab CRUD (nested under contract)

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| POST | `/contracts/{contract_id}/slabs` | `contract.update` | Add a slab |
| PUT | `/contracts/{contract_id}/slabs/{slab_id}` | `contract.update` | Update a slab |
| DELETE | `/contracts/{contract_id}/slabs/{slab_id}` | `contract.update` | Remove a slab |

### Cost Calculation

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| POST | `/contracts/calculate/{route_id}` | `contract.read` | Calculate cost for a completed route |

**Calculate cost endpoint logic:**

1. Fetch `RouteManagement` by `route_id`
   - Validate `status == COMPLETED`
   - Extract `actual_total_distance`, `assigned_vehicle_id`

2. Fetch `Vehicle` by `assigned_vehicle_id`
   - Validate `contract_id` is not null
   - Extract `vehicle_type_id`

3. Fetch `Contract` by `vehicle.contract_id`
   - Validate contract is active
   - Extract `contract_name`, `vendor_id`

4. Fetch all active `ContractSlab` rows for this contract
   - Ordered by `min_km ASC`
   - Validate at least one slab exists

5. **Progressive slab calculation:**
   ```
   remaining_distance = actual_total_distance
   sorted_slabs = slabs ORDER BY min_km ASC

   for each slab:
       slab_end = slab.max_km if slab.max_km else INFINITY
       km_in_slab = min(remaining_distance, slab_end - slab.min_km)

       if km_in_slab <= 0:
           continue  # skip (e.g. slab range doesn't overlap with distance)

       cost_in_slab = km_in_slab × slab.rate
       total_cost += cost_in_slab
       breakdown.append({ min_km, max_km, km_used, rate, cost: cost_in_slab })
       remaining_distance -= km_in_slab

       if remaining_distance <= 0:
           break

   effective_rate = round(total_cost / actual_total_distance, 2)
   ```

6. Return `CostCalcResponse`

**Example calculation (18 km, slabs: 0–10 @ ₹10, 10–20 @ ₹15):**

| Slab | Min Km | Max Km | Km Used | Rate | Cost |
|------|--------|--------|---------|------|------|
| 1 | 0 | 10 | 10.0 | ₹10 | ₹100 |
| 2 | 10 | 20 | 8.0 | ₹15 | ₹120 |
| **Total** | | | **18.0** | **₹12.22/km** | **₹220** |

---

## Data Flow

```
                       ┌─────────────────┐
                       │    Vendor       │
                       │  (vendor_id)    │
                       └────────┬────────┘
                                │
                       ┌────────▼────────┐      ┌─────────────────────┐
                       │   Contract      │──────│   CostCenter        │
                       │  (contract_id)  │      │   (future module)   │
                       └────────┬────────┘      └─────────────────────┘
                                │
                       ┌────────▼────────┐
                       │  ContractSlab   │
                       │  min_km, max_km │
                       │  rate           │
                       └────────┬────────┘
                                │
    ┌───────────────────────────┼───────────────────────────┐
    │                           │                           │
    ▼                           ▼                           ▼
┌────────────┐          ┌──────────────┐           ┌──────────────┐
│  Vehicle   │          │  VehicleType │           │  RouteMgmt   │
│ contract_id│──────────│ (vehicle_type│           │ actual_total │
│ vehicle_ty │          │    _id)      │           │ _distance    │
└────────────┘          └──────────────┘           └──────────────┘
```

### End-to-End Cost Calculation Walkthrough

```
POST /api/v1/contracts/calculate/42

route_id=42
    │
    ▼
RouteManagement ──► actual_total_distance = 18.0
    │                  assigned_vehicle_id = 15
    │                  status = COMPLETED
    │
    ▼
Vehicle(15) ──► contract_id = 1
    │             vehicle_type_id = 2  →  "SEDAN"
    │
    ▼
Contract(1) ──► contract_name = "Sedan City Contract"
    │              vendor_id = 3
    │              is_active = True
    │
    ▼
ContractSlabs(ORDER BY min_km) ──► [
    │                                  {min_km:0, max_km:10, rate:10},
    │                                  {min_km:10, max_km:20, rate:15}
    │                              ]
    │
    ▼
Progressive Calculation:
    Slab 1: 0-10km,  km_used=10.0,  cost = 10×10  = ₹100
    Slab 2: 10-20km, km_used=8.0,   cost = 8×15   = ₹120
    ─────────────────────────────────────────────────────
    Total:              18.0 km                = ₹220
    Effective Rate:     220/18                 = ₹12.22/km
    │
    ▼
Response:
{
  "status": "success",
  "data": {
    "route_id": 42,
    "contract_id": 1,
    "contract_name": "Sedan City Contract",
    "vehicle_id": 15,
    "vehicle_type_name": "SEDAN",
    "vendor_id": 3,
    "total_distance_km": 18.0,
    "total_cost": 220.0,
    "effective_rate": 12.22,
    "slab_breakdown": [
      {"min_km": 0,   "max_km": 10, "km_used": 10.0, "rate": 10.0, "cost": 100.0},
      {"min_km": 10,  "max_km": 20, "km_used": 8.0,  "rate": 15.0, "cost": 120.0}
    ]
  },
  "message": "Route cost calculated successfully"
}
```

---

## Edge Cases & Validations

| Scenario | Handling |
|----------|----------|
| Route not found | HTTP 404 |
| Route status is not COMPLETED | HTTP 400 — "Route is not completed" |
| Vehicle has no contract assigned | HTTP 400 — "Vehicle has no contract assigned" |
| Contract is inactive | HTTP 400 — "Contract is inactive" |
| No active slabs on contract | HTTP 400 — "No active slabs found for this contract" |
| Distance exceeds last slab's max_km | Last slab with `max_km=NULL` acts as catch-all (infinity) |
| Gap between slabs (e.g. 0–5, 10–15) | Blocked at creation time — service validates contiguity |
| Overlapping slabs | Blocked by `UNIQUE(contract_id, min_km)` + service validation |
| `min_km >= max_km` | Rejected by Pydantic field validator |
| `rate <= 0` | Rejected by Pydantic field validator |

---

## Migration Plan

**New migration:** `20260611_1300_add_contract_tables.py`
- **Revises:** `20260611_remove_costing`
- **Operations:**
  1. Create `contracts` table (`cost_center_id` is nullable integer only for now)
  2. Create `contract_slabs` table
  3. Add `contract_id` column to `vehicles`
  4. Add foreign key: `vehicles.contract_id → contracts.contract_id`

---

## Registration Steps

**`app/models/__init__.py`** — add:
```python
from app.models.contract import Contract, ContractSlab
```

**`app/routes/__init__.py`** — add:
```python
from app.routes.contract_router import router as contract_router
```

**`app/api.py`** — add:
```python
from app.routes import contract_router

api_router.include_router(contract_router, prefix=V1)
```

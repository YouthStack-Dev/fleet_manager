# Driver App API Flow - Updated Design

## Overview
The driver endpoints have been redesigned to separate **duty management** from **trip operations**. This ensures drivers follow a clear workflow and prevents conflicting route states.

---

## New Endpoint Flow

### 1. **GET /driver/trips** ✅ (Unchanged)
- **Purpose**: Fetch driver's routes by status (upcoming/ongoing/completed)
- **Filters**: 
  - `upcoming` → DRIVER_ASSIGNED routes
  - `ongoing` → ONGOING routes (no date filter for edge cases)
  - `completed` → COMPLETED routes
- **Returns**: Route list with stops, bookings, vehicle/driver details

---

### 2. **POST /driver/duty/start** 🆕 (New)
- **Purpose**: Start driver's duty on a specific route
- **Flow**:
  1. Validates route is in `DRIVER_ASSIGNED` state
  2. Checks driver has NO other `ONGOING` routes
  3. Changes route status: `DRIVER_ASSIGNED` → `ONGOING`
- **Validations**:
  - Route must belong to driver
  - Route must be in `DRIVER_ASSIGNED` state
  - Driver cannot have another ongoing route
- **Response**:
  ```json
  {
    "route_id": 123,
    "route_status": "Ongoing"
  }
  ```
- **Idempotent**: Returns success if already ONGOING

---

### 3. **POST /driver/trip/start** ✅ (Updated)
- **Purpose**: Mark passenger pickup (employee boards vehicle)
- **Prerequisites**: Route must be `ONGOING` (duty started)
- **Flow**:
  1. Validates route is `ONGOING`
  2. Verifies driver location near pickup
  3. Validates boarding OTP (if required)
  4. Changes booking status: `REQUEST/SCHEDULED` → `ONGOING`
  5. Sets `actual_pick_up_time`
- **Validations**:
  - Route must be in `ONGOING` state
  - Booking must be part of the route
  - Previous stops must be completed/no-show
  - Driver location within 500m of pickup
  - OTP verification (if required)
- **Response**: Booking status + next stop details
- **Note**: Does NOT change route status (already ONGOING)

---

### 4. **PUT /driver/trip/drop** ✅ (Updated)
- **Purpose**: Mark passenger drop-off (employee exits vehicle)
- **Flow**:
  1. Validates route is `ONGOING`
  2. Verifies driver location near drop point
  3. Validates deboarding OTP (if required)
  4. Changes booking status: `ONGOING` → `COMPLETED`
  5. Sets `actual_drop_time`
- **Validations**:
  - Route must be in `ONGOING` state
  - Booking must be in `ONGOING` status
  - Driver location within 500m of drop
  - OTP verification (if required)
- **Response**: Booking status
- **Important**: Does NOT auto-complete route (only marks booking complete)

---

### 5. **PUT /driver/trip/no-show** ✅ (Updated)
- **Purpose**: Mark employee as no-show (didn't board)
- **Flow**:
  1. Validates booking is not already `ONGOING` or `COMPLETED`
  2. Checks previous stops are done
  3. Changes booking status: `REQUEST/SCHEDULED` → `NO_SHOW`
  4. Sets `actual_pick_up_time` (for tracking)
  5. Records reason
- **Validations**:
  - Route must belong to driver
  - Booking cannot be ONGOING or COMPLETED
  - Previous stops must be finished
- **Response**: Booking status + next stop details
- **Important**: Does NOT change route status (remains `ONGOING`)

---

### 6. **PUT /driver/duty/end** 🆕 (Renamed from /trip/end)
- **Purpose**: End driver's duty and close the route
- **Flow**:
  1. Validates route is `ONGOING`
  2. Processes all remaining bookings:
     - `ONGOING` bookings → `COMPLETED` (passengers still onboard)
     - Other bookings → `NO_SHOW` (missed pickups)
  3. Changes route status: `ONGOING` → `COMPLETED`
  4. Sets `actual_end_time`
- **Validations**:
  - Route must be in `ONGOING` state
  - Route must belong to driver
- **Response**:
  ```json
  {
    "route_id": 123,
    "route_status": "Completed",
    "marked_completed": 5,
    "marked_no_show": 2
  }
  ```
- **Idempotent**: Returns success if already COMPLETED

---

## Key Rules & Constraints

### ✅ Driver Cannot Have Multiple Ongoing Routes
- `/duty/start` checks for existing `ONGOING` routes
- Prevents conflicts and ensures focus on one route at a time

### ✅ Route State Progression (Cannot Revert)
```
DRIVER_ASSIGNED → (start duty) → ONGOING → (end duty) → COMPLETED
```
- Once `ONGOING`, route cannot go back to `DRIVER_ASSIGNED`
- Only `end_duty` can mark route as `COMPLETED`

### ✅ Booking Operations Require ONGOING Route
- `/trip/start` (pickup), `/trip/drop`, `/trip/no-show` all require route to be `ONGOING`
- Driver must call `/duty/start` first

### ✅ Route Completion Only via end_duty
- Individual drop/no-show operations do NOT complete the route
- Route stays `ONGOING` until driver explicitly calls `/duty/end`
- Allows driver to handle unexpected situations (late passengers, etc.)

---

## Migration from Old Flow

### Old Behavior (Removed)
- ❌ `/start` used to set route `ONGOING` AND mark first booking
- ❌ `/trip/drop` auto-completed route when all bookings done
- ❌ `/trip/no-show` could auto-complete single-booking routes

### New Behavior (Current)
- ✅ `/duty/start` sets route `ONGOING` (separate step)
- ✅ `/trip/start` only handles booking pickup
- ✅ `/trip/drop` only marks booking completed
- ✅ `/trip/no-show` only marks booking no-show
- ✅ `/duty/end` explicitly completes route

---

## Example Workflow

### Typical Happy Path
```
1. Driver logs in and views routes:
   GET /driver/trips?status_filter=upcoming
   
2. Driver starts duty for route 123:
   POST /driver/duty/start?route_id=123
   → Route: DRIVER_ASSIGNED → ONGOING
   
3. Driver picks up first passenger (booking 456):
   POST /driver/trip/start?route_id=123&booking_id=456&otp=1234
   → Booking 456: SCHEDULED → ONGOING
   
4. Driver drops first passenger:
   PUT /driver/trip/drop?route_id=123&booking_id=456&otp=5678
   → Booking 456: ONGOING → COMPLETED
   
5. Second passenger is no-show:
   PUT /driver/trip/no-show?route_id=123&booking_id=457&reason=Not at pickup
   → Booking 457: SCHEDULED → NO_SHOW
   
6. Driver completes all stops and ends duty:
   PUT /driver/duty/end?route_id=123
   → Route: ONGOING → COMPLETED
   → Any remaining bookings marked appropriately
```

### Edge Case: Early Route Termination
```
1. Driver starts duty:
   POST /driver/duty/start?route_id=123
   
2. Emergency situation - driver needs to end:
   PUT /driver/duty/end?route_id=123&reason=Vehicle breakdown
   → Route: ONGOING → COMPLETED
   → Pending bookings marked NO_SHOW
   → ONGOING bookings marked COMPLETED
```

---

## Frontend Integration Notes

1. **Check ongoing route before allowing new duty start**
2. **Disable pickup/drop/no-show buttons until duty is started**
3. **Show "End Duty" button only when route is ONGOING**
4. **Handle idempotent responses gracefully**

---

## Testing Checklist

- [ ] Cannot start duty on route already ONGOING (idempotent)
- [ ] Cannot start duty when another route is ONGOING
- [ ] Cannot pickup without starting duty first
- [ ] Cannot drop without starting duty first
- [ ] Dropping does NOT auto-complete route
- [ ] No-show does NOT change route status
- [ ] End duty completes route and processes all bookings
- [ ] Location validation works for pickup/drop
- [ ] OTP validation works for boarding/deboarding

---

**Version**: 2.0  
**Last Updated**: December 11, 2025  
**Status**: ✅ Implemented & Syntax Validated

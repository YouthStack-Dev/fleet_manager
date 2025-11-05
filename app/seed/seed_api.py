import uuid
from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Depends, Header, Query
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
import random
import requests
import logging
import os
import math

from common_utils.auth.permission_checker import PermissionChecker

router = APIRouter(prefix="/admin/seed", tags=["Admin Seeder"])

DEFAULT_PASSWORD = "Pass@123"
MAX_WORKERS = 10
MAX_EMPLOYEES_PER_REQ = 200

logging.basicConfig(level=logging.INFO)



@router.post("/employees", status_code=status.HTTP_202_ACCEPTED)
async def trigger_seeding(
    background_tasks: BackgroundTasks,
    tenant_id: str = Query(...),
    num: int = Query(..., gt=0),
    team_id: Optional[int] = Query(None),
    api_url: str = Query(..., description="Backend base URL"),
    access_token: str = Header(..., alias="Authorization", description="Bearer token"),
    _: bool =True,
):
    if num > MAX_EMPLOYEES_PER_REQ:
        raise HTTPException(400, f"Max allowed: {MAX_EMPLOYEES_PER_REQ}")

    # Add background task
    background_tasks.add_task(
        run_seeder,
        tenant_id,
        num,
        team_id,
        api_url,
        access_token
    )

    return {
        "status": "queued",
        "tenant_id": tenant_id,
        "count": num,
        "team_id": team_id
    }


def headers(token: str):
    return {
        "Content-Type": "application/json",
        "Authorization": token
    }


def email_exists(email: str, tenant_id: str, api_url: str, token: str) -> bool:
    resp = requests.get(
        f"{api_url}/api/v1/employees/check?email={email}&tenant_id={tenant_id}",
        headers=headers(token)
    )
    return resp.status_code == 200

ADDRESSES = [
    {"address": "3rd Cross, 27th Main Rd, 1st Sector, HSR Layout, Bengaluru 560102", "lat":12.91198, "lon":77.63875},
    {"address": "2nd Cross, 1st Main Rd, Soudamini Layout, Konanakunte, Bengaluru 560062", "lat":12.88568, "lon":77.57321},
    {"address": "2nd Main Rd, Opp Varalakshmi Hospital, Madiwala Ext, BTM, Bengaluru 560068", "lat":12.91518, "lon":77.61146},
    {"address": "8th Cross Rd, 1st Sector, HSR Layout, Bengaluru 560102", "lat":12.91595, "lon":77.63482},
    {"address": "1st Cross, Central Jail Rd, Naganathapura, Hosa Rd, Bengaluru 560100", "lat":12.87188, "lon":77.65829},
    {"address": "Kada Agrahara, Sarjapur-Marathahalli Rd", "lat":12.90948, "lon":77.75076},
    {"address": "Bellandur Main Rd, Bellandur, Bengaluru 560103", "lat":12.93536, "lon":77.67819},
    {"address": "Bellandur Main Rd, Bellandur, Bengaluru 560103", "lat":12.93495, "lon":77.67650},
    {"address": "Brigade Cornerstone Utopia, Varthur 560087", "lat":12.95364, "lon":77.75105},
    {"address": "KT Silk Sarees, Dommasandra, Thigala Chowdadenahalli 562125", "lat":12.87943, "lon":77.73863},
    {"address": "Ashirvad Colony, Horamavu, Bengaluru", "lat":13.03407, "lon":77.66441},
    {"address": "Heelalige Gate, Chandapura, Bengaluru 560099", "lat":12.80898, "lon":77.70554}
]
ADDR_COUNT = len(ADDRESSES)

def generate_payload(i: int, tenant_id: str, team_id: Optional[int]):
    first_names = ["John", "Sara", "Mike", "Priya", "Ravi", "Kiran", "Aman", "Anita"]
    last_names = ["Shah", "Reddy", "Patel", "Singh", "Verma", "Das"]

    name = f"{random.choice(first_names)} {random.choice(last_names)}"
    email = f"{tenant_id[:3].upper()}{uuid.uuid4().hex[:4].upper()}@gmail.com"

    # deterministic address index (i-1 to zero-base)
    idx = (i - 1) % ADDR_COUNT
    addr = ADDRESSES[idx]

    return {
        "name": name,
        "email": email,
        "phone": f"+91{random.randint(7000000000, 9999999999)}",
        "employee_code": f"{tenant_id[:3].upper()}{uuid.uuid4().hex[:4].upper()}",
        "password": DEFAULT_PASSWORD,
        "tenant_id": tenant_id,
        "team_id": team_id,
        "is_active": True,

        "address": addr["address"],
        "latitude": addr["lat"],
        "longitude": addr["lon"],
        
        "gender": random.choice(["Male", "Female"])
    }

def create_employee(i: int, tenant_id: str, team_id: Optional[int], api_url: str, token: str):
    payload = generate_payload(i, tenant_id, team_id)

    if email_exists(payload["email"], tenant_id, api_url, token):
        logging.warning(f"Duplicate: {payload['email']}")
        return "skipped"

    resp = requests.post(
        f"{api_url}/api/v1/employees/",
        json=payload,
        headers=headers(token),
        timeout=15
    )

    if resp.status_code in (200, 201):
        logging.info(f"✓ Created: {payload['email']}")
        return "success"

    logging.error(f"✗ Failed: {payload['email']} -> {resp.text}")
    return "error"


def run_seeder(tenant_id: str, num: int, team_id: Optional[int], api_url: str, token: str):
    logging.info(f"Seeder started -> tenant={tenant_id}, num={num}, team={team_id}")

    results = {"success": 0, "skipped": 0, "error": 0}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        tasks = [
            executor.submit(create_employee, i, tenant_id, team_id, api_url, token)
            for i in range(1, num + 1)
        ]

        for f in as_completed(tasks):
            status = f.result()
            results[status] += 1

    logging.info(f"Seeder results -> {results}")



@router.post("/bookings", status_code=status.HTTP_202_ACCEPTED, tags=["Admin Seeder"])
async def trigger_booking_seeding(
    background_tasks: BackgroundTasks,
    tenant_id: str = Query(...),
    from_date: str = Query(..., regex="^\\d{4}-\\d{2}-\\d{2}$"),
    to_date: str = Query(..., regex="^\\d{4}-\\d{2}-\\d{2}$"),
    shift_id: int = Query(...),
    team_id: Optional[int] = Query(None),
    api_url: str = Query(...),
    access_token: str = Header(..., alias="Authorization")
):
    background_tasks.add_task(
        run_booking_seeder,
        tenant_id,
        from_date,
        to_date,
        shift_id,
        team_id,
        api_url,
        access_token
    )
    return {
        "status": "queued",
        "tenant_id": tenant_id,
        "from": from_date,
        "to": to_date,
        "shift_id": shift_id,
        "team_id": team_id
    }
import requests
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_WORKERS = 8
DEFAULT_TIMEOUT = 10
WEEKOFF = {5, 6}  # Sat=5, Sun=6


def iso_date_range(from_date: str, to_date: str):
    start = datetime.strptime(from_date, "%Y-%m-%d")
    end = datetime.strptime(to_date, "%Y-%m-%d")
    while start <= end:
        if start.weekday() not in WEEKOFF:
            yield start.strftime("%Y-%m-%d")
        start += timedelta(days=1)


def get_employees(api_url, tenant_id, team_id, headers):
    emp = []
    skip = 0
    limit = 100
    while True:
        params = {"tenant_id": tenant_id, "skip": skip, "limit": limit}
        if team_id:
            params["team_id"] = team_id
        r = requests.get(f"{api_url}/api/v1/employees/", headers=headers, params=params)
        if r.status_code != 200:
            break
        items = r.json().get("data", {}).get("items", [])
        if not items:
            break
        emp.extend(items)
        skip += limit
    return emp


def create_booking_bulk(api_url, tenant_id, emp_id, dates, shift_id, headers):
    payload = {
        "tenant_id": tenant_id,
        "employee_id": emp_id,
        "booking_dates": dates,
        "shift_id": shift_id
    }
    r = requests.post(f"{api_url}/api/v1/bookings/", json=payload, headers=headers, timeout=DEFAULT_TIMEOUT)
    return r.status_code, r.text


def create_booking_single(api_url, tenant_id, emp_id, date, shift_id, headers):
    payload = {
        "tenant_id": tenant_id,
        "employee_id": emp_id,
        "booking_date": date,
        "shift_id": shift_id
    }
    r = requests.post(f"{api_url}/api/v1/bookings/", json=payload, headers=headers, timeout=DEFAULT_TIMEOUT)
    return r.status_code, r.text


def process_employee(emp, api_url, tenant_id, dates, shift_id, headers):
    emp_id = emp.get("employee_id") or emp.get("id")
    if not emp_id:
        return {"emp": None, "success": 0, "fail": len(dates)}

    # Try bulk first:
    status, body = create_booking_bulk(api_url, tenant_id, emp_id, dates, shift_id, headers)
    if status in (200, 201):
        return {"emp": emp_id, "success": len(dates), "fail": 0}

    # Fallback per-date:
    success = 0
    fail = 0
    for d in dates:
        s, _ = create_booking_single(api_url, tenant_id, emp_id, d, shift_id, headers)
        if s in (200, 201):
            success += 1
        else:
            fail += 1
    return {"emp": emp_id, "success": success, "fail": fail}


def run_booking_seeder(tenant_id, from_date, to_date, shift_id, team_id, api_url, token):
    logging.info(f"Booking seeding started tenant={tenant_id}")

    headers = {"Authorization": token, "Content-Type": "application/json"}
    dates = list(iso_date_range(from_date, to_date))
    employees = get_employees(api_url, tenant_id, team_id, headers)

    results = {"success": 0, "failed": 0, "dates": dates}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futures = [
            exe.submit(process_employee, emp, api_url, tenant_id, dates, shift_id, headers)
            for emp in employees
        ]
        for fut in as_completed(futures):
            r = fut.result()
            results["success"] += r["success"]
            results["failed"] += r["fail"]

    logging.info(f"Booking Seeder Done -> {results}")

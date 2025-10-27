from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Depends, Header, Query
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
import random
import requests
import logging
import os

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


def generate_payload(i: int, tenant_id: str, team_id: Optional[int]):
    first_names = ["John", "Sara", "Mike", "Priya", "Ravi", "Kiran", "Aman", "Anita"]
    last_names = ["Shah", "Reddy", "Patel", "Singh", "Verma", "Das"]
    
    name = f"{random.choice(first_names)} {random.choice(last_names)}"

    email = f"seed{i}@{tenant_id.lower()}.com"
    return {
        "name": name,
        "email": email,
        "phone": f"+91{random.randint(7000000000, 9999999999)}",
        "employee_code": f"EMP{i:04d}",
        "password": DEFAULT_PASSWORD,
        "tenant_id": tenant_id,
        "team_id": team_id,
        "is_active": True,
        "latitude": 12.9352 + random.uniform(-0.01, 0.01),
        "longitude": 77.6245 + random.uniform(-0.01, 0.01),
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

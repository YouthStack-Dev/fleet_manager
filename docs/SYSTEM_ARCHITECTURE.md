# System Architecture

This document summarizes how Fleet Manager is put together so new contributors can quickly see how requests move through the system.

## High-level view

```mermaid
flowchart LR
    subgraph Clients
        AdminUI[Admin UI / Postman]
        EmpApp[Employee app]
        DriverApp[Driver app]
    end

    Clients --> API[FastAPI service\n(main.py + routers)]
    API --> DB[(PostgreSQL\nSQLAlchemy/Alembic)]
    API --> Redis[(Redis cache & distributed locks)\n(enabled when USE_REDIS=1)]
    API --> Storage[(StorageService via fsspec\nlocal / S3 / GCS / Azure)]
    API --> Firebase[Firebase RTDB / FCM\nDriver location updates]
    API --> Email[SMTP provider\nemail_service]
    API --> Monitoring[DB monitoring & health\napp.utils.database_monitor]
    API --> Logs[Structured logging\napp/core/logging_config]
```

## Core components

- **API layer:** `main.py` bootstraps FastAPI, applies CORS, and wires domain routers for employees, drivers, bookings, tenants, vendors, vehicles, alerts (SOS), IAM, monitoring, and reports under `/api/v1`.
- **Business/CRUD layer:** Domain logic is organized under `app/crud`, `app/services`, and `app/utils`, keeping routing thin.
- **Data layer:** PostgreSQL via SQLAlchemy models (`app/models`) with Alembic migrations (`migrations/`). Seed helpers live in `app/seed`.
- **Auth:** JWT/OAuth2 endpoints live in `app/routes/auth_router.py` with token/config settings drawn from `app/config.py` (`SECRET_KEY`, `TOKEN_EXPIRY_HOURS`, `OAUTH2_URL`, `OAUTH2_ENV`, `X_INTROSPECT_SECRET`).
- **Storage:** `StorageService` (`app/services/storage_service.py`) abstracts file handling through fsspec. Environment variables choose filesystem or cloud backends.
- **Caching / async primitives:** Optional Redis (`USE_REDIS=1`) for caching/locks; connection settings in `app/config.py`.
- **Notifications:** SMTP email helper (`app/core/email_service.py`) drives system notifications (onboarding, routine alerts, SOS); SOS alert flows are under `app/routes/alert_router.py`.
- **Driver location:** Firebase integration (`app/firebase`) pushes driver coordinates; requires a mounted Firebase key in `app/firebase/firebase_key.json`.
- **Observability:** Centralized structured logging (`app/core/logging_config.py`) and periodic DB monitoring (`app/utils/database_monitor.py`).

## Deployment topology

- **Docker Compose (local/dev):** `docker-compose.yml` brings up PostgreSQL, Redis, and the `fleet_api` service. Environment variables in compose files and `service.*.env` files control database, auth, email, storage, and Redis settings.
- **App container:** Runs `uvicorn` exposing FastAPI on port `8000`; mounts the codebase and optional secrets (e.g., Firebase key).
- **Data services:** PostgreSQL persists to the `postgres_data` volume; Redis (when enabled) persists to `redis_data`.

## Request and data flow

1. Clients call `fleet_api` endpoints (e.g., `/api/v1/driver`, `/api/v1/booking`).
2. Routers validate payloads using Pydantic schemas (`app/schemas`) and delegate to CRUD/service helpers.
3. Database interactions go through SQLAlchemy sessions from `app/database/session.py`; migrations keep schema in sync.
4. Side-effects are dispatched as needed:
   - Files saved through `StorageService`
   - Emails via `app/core/email_service.py`
   - Driver locations synced to Firebase
   - Optional Redis usage for caching/locks
5. Logging and monitoring capture request/DB health for troubleshooting.

Use this map to locate the relevant module before making changes; most domain-specific behavior lives in `app/routes`, `app/crud`, and `app/services`.

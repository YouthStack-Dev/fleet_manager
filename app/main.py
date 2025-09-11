from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import uvicorn

from database.session import get_db
from sqlalchemy.orm import Session
from routes import admin_router, employee_router, driver_router, booking_router

app = FastAPI(
    title="Fleet Manager API",
    description="API for Fleet Management System",
    version="1.0.0",
)

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(admin_router.router, prefix="/api/v1")
app.include_router(employee_router.router, prefix="/api/v1")
app.include_router(driver_router.router, prefix="/api/v1")
app.include_router(booking_router.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "Welcome to Fleet Manager API"}


@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    try:
        # Try to execute a simple query to check DB connection
        db.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {str(e)}"
        )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

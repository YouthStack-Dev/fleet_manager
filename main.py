import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import api_router
from database.session import engine, Base

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Fleet Manager API",
    description="API for managing fleet operations",
    version="1.0.0",
)

# Set up CORS
origins = [
    "http://localhost",
    "http://localhost:3000",  # React frontend
    "http://localhost:8080",  # Vue frontend
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router)

@app.get("/")
async def root():
    return {
        "message": "Welcome to Fleet Manager API",
        "docs_url": "/docs",
        "redoc_url": "/redoc"
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.database import router as database_router

app = FastAPI(
    title="AI Form Assistant API",
    description="AI-powered document extraction and form autofill",
    version="0.2.0"
)

origins = [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    database_router,
    prefix="/api/v1/database",
    tags=["Database"]
)


@app.get("/")
async def root():
    return {
        "message": "AI Form Assistant API",
        "status": "running"
    }


@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy"}
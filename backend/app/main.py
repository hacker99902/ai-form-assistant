from contextlib import asynccontextmanager
from app.api.auth import router as auth_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.core.config import settings
from app.api.database import router as database_router
from app.api.documents import router as documents_router
from app.core.database import pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Opening Neon PostgreSQL connection pool...")
    pool.open(wait=True)

    try:
        print("Neon connection pool ready!")
        yield
    finally:
        pool.close()
        print("Neon connection pool closed.")


app = FastAPI(
    title="AI Form Assistant API",
    description="AI-powered document extraction and form autofill",
    version="0.2.0",
    lifespan=lifespan,
)



app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET,
    same_site="lax",
    https_only=False,  # Local development only
)

app.include_router(
    database_router,
    prefix="/api/v1/database",
    tags=["Database"],
)

app.include_router(
    documents_router,
    prefix="/api/v1/documents",
    tags=["Documents"],
)
app.include_router(
    auth_router,
    prefix="/api/v1/auth",
    tags=["Authentication"],
)

@app.get("/")
async def root():
    return {
        "message": "AI Form Assistant API",
        "status": "running",
    }


@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy"}

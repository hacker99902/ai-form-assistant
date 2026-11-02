
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AI Form Assistant API",
    description="AI-powered document extraction and form autofill",
    version="0.1.0",
)

# Frontend development server
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "message": "Welcome to AI Form Assistant API",
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "AI Form Assistant Backend",
    }

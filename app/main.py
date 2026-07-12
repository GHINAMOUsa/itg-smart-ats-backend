from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine
from app.routes import auth, jobs, candidates, applications, uploads

# Create tables if they don't already exist. In production, prefer running
# `alembic upgrade head` instead of relying on this call.
Base.metadata.create_all(bind=engine)

Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="ITG Career System API",
    description="Backend API for the ITG Career System recruitment platform.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(candidates.router)
app.include_router(applications.router)
app.include_router(uploads.router)


@app.get("/api/health", tags=["Health"])
def health_check():
    return {"status": "ok"}

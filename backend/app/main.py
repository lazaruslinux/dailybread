from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  (imported so its tables register on Base)
from app.config import settings
from app.db import Base, db_ok, engine
from app.routers import auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create any missing tables on startup. Fine for now; we'll switch to
    # Alembic migrations before real family data lives in the DB.
    if engine is not None:
        Base.metadata.create_all(engine)
    yield


app = FastAPI(title="dailybread", version="0.0.1", lifespan=lifespan)

# Allow the Vite dev server to call the API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)


@app.get("/")
def root():
    return {"app": "dailybread", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok", "mode": settings.app_mode, "demo": settings.demo_mode}


@app.get("/health/db")
def health_db(response: Response):
    ok, detail = db_ok()
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"db": "ok" if ok else "error", "detail": detail}

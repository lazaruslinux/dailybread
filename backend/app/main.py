from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import db_ok

app = FastAPI(title="dailybread", version="0.0.1")

# Allow the Vite dev server to call the API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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

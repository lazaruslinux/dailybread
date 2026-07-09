import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import push as push_engine
from app.config import settings
from app.db import db_ok
from app.routers import (
    auth,
    diary,
    families,
    foods,
    grocery,
    health,
    items,
    meals,
    push,
    recipes,
    users,
    villages,
)

# Schema management moved to Alembic: the container entrypoint runs
# "alembic upgrade head" before starting the server, so by the time the app
# is up the database is guaranteed to be current.


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The reminder loop runs only when push is configured (VAPID keys set);
    # without it the app behaves exactly as before.
    task = asyncio.create_task(push_engine.reminder_loop()) if push_engine.enabled() else None
    yield
    if task is not None:
        task.cancel()


app = FastAPI(title="dailybread", version="0.0.1", lifespan=lifespan)

# Allow the Vite dev server to call the API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CSRF defense-in-depth. Our session cookie is SameSite=lax, which already
# stops browsers from attaching it to cross-site POSTs. This middleware adds a
# second, independent lock: modern browsers label every request with where it
# came from (Sec-Fetch-Site), and we refuse state-changing requests that a
# browser says originated on someone else's site. Non-browser clients (curl,
# tests) don't send the header and are unaffected.
@app.middleware("http")
async def block_cross_site_writes(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site request refused"}, status_code=403)
    return await call_next(request)


app.include_router(auth.router)
app.include_router(diary.router)
app.include_router(health.router)
app.include_router(families.router)
app.include_router(grocery.router)
app.include_router(items.router)
app.include_router(foods.router)
app.include_router(meals.router)
app.include_router(push.router)
app.include_router(recipes.router)
app.include_router(users.router)
app.include_router(villages.router)


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

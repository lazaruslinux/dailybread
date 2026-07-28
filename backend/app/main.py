import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from app import push as push_engine
from app.config import check_deploy_config, settings
from app.db import db_ok
from app.routers import (
    auth,
    diary,
    families,
    fitness,
    foods,
    grocery,
    health,
    inbox,
    items,
    meals,
    push,
    recipes,
    users,
    verses,
    villages,
)

# Schema management moved to Alembic: the container entrypoint runs
# "alembic upgrade head" before starting the server, so by the time the app
# is up the database is guaranteed to be current.

# Refuse to serve with the repo's placeholder secrets; failing the import
# stops uvicorn before it ever binds.
check_deploy_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The reminder loop runs only when push is configured (VAPID keys set);
    # without it the app behaves exactly as before.
    task = asyncio.create_task(push_engine.reminder_loop()) if push_engine.enabled() else None
    yield
    if task is not None:
        task.cancel()


app = FastAPI(title="dailybread", version="0.0.1", lifespan=lifespan)

# No CORS middleware, deliberately. The browser reaches the API through the
# same origin in every path: nginx in production, the Vite proxy in
# development, so the API never needs to answer a cross-origin request. An
# earlier allowance for the dev server on port 5173 was removed because
# SameSite keys on the domain and ignores the port, which made a page on
# localhost:5173 same-site to the API and let it read responses with the
# user's session.

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


# Request-body ceilings, enforced before anything parses the body. The bundled
# nginx caps /api at 15 MB, but a self-hoster who fronts uvicorn with something
# else (or nothing) previously had no limit at all. The ingest cap matches the
# nginx front door so a big (authenticated: the token is checked before the
# body is read) catch-up export behaves identically with or without the proxy.
MAX_BODY_BYTES = 16 * 1024 * 1024
INGEST_MAX_BODY_BYTES = 15 * 1024 * 1024
_BODY_CAPS = {"/ingest/health": INGEST_MAX_BODY_BYTES}


class _BodyTooLarge(Exception):
    pass


async def _send_413(send) -> None:
    body = b'{"detail":"Request body too large"}'
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class BodySizeLimitMiddleware:
    """Pure ASGI so it runs outside body parsing entirely: an honest
    Content-Length is refused up front, and a chunked body is counted and cut
    off at the cap while it streams."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        cap = _BODY_CAPS.get(scope.get("path", ""), MAX_BODY_BYTES)
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > cap:
                    await _send_413(send)
                    return
            except ValueError:
                pass  # nonsense header; the streamed count below still guards
        received = 0
        too_large = False
        response_started = False

        async def counting_receive():
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > cap:
                    too_large = True
                    raise _BodyTooLarge
            return message

        async def tracking_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                # FastAPI reads bodies inside its own try/except and reports
                # our mid-stream cut as its generic parse-error 400; once the
                # flag is set that 400 can only mean "too large", so give the
                # client the honest status.
                if too_large and message["status"] == 400:
                    message = {**message, "status": 413}
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLarge:
            if response_started:
                raise
            await _send_413(send)


app.add_middleware(BodySizeLimitMiddleware)


app.include_router(auth.router)
app.include_router(diary.router)
app.include_router(health.router)
app.include_router(inbox.router)
app.include_router(families.router)
app.include_router(fitness.router)
app.include_router(grocery.router)
app.include_router(items.router)
app.include_router(foods.router)
app.include_router(meals.router)
app.include_router(push.router)
app.include_router(recipes.router)
app.include_router(users.router)
app.include_router(verses.router)
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

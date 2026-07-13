from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.db import init_db
from app.routers import auth, billing, chat, keys, me, models, projects, github, studio_fs

settings = get_settings()
ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    await init_db()
    await _migrate_balances_to_rub()
    # Best-effort catalog: never block startup on network sync
    try:
        from app.catalog import reload_catalog
        from app.kie_sync import KIE_MODELS_PATH, sync_kie_catalog
        from app.polza_sync import sync_polza_prices
        import asyncio

        async def _refresh_catalog() -> None:
            if not KIE_MODELS_PATH.exists():
                await sync_kie_catalog()
            await sync_polza_prices()
            reload_catalog()

        if KIE_MODELS_PATH.exists():
            reload_catalog()
            asyncio.create_task(_refresh_catalog())
        else:
            # First boot: need local file before serving models
            try:
                await asyncio.wait_for(_refresh_catalog(), timeout=25)
            except Exception:
                reload_catalog()
    except Exception:
        pass
    yield


async def _migrate_balances_to_rub() -> None:
    """One-shot: old accounts stored USD in balance_usd / cost_user_usd."""
    marker = ROOT / "data" / ".currency_rub"
    if marker.exists():
        return
    from sqlalchemy import text

    from app.db import engine

    rate = settings.USD_RUB
    async with engine.begin() as conn:
        await conn.execute(text(f"UPDATE users SET balance_usd = balance_usd * {rate}"))
        await conn.execute(text(f"UPDATE usage_logs SET cost_user_usd = cost_user_usd * {rate}"))
        await conn.execute(text(f"UPDATE messages SET cost_user_usd = cost_user_usd * {rate}"))
    marker.write_text("ok\n", encoding="utf-8")


app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NoCacheFrontendMiddleware(BaseHTTPMiddleware):
    """Prevent stale Studio UI from browser disk cache during rapid iteration."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/app" or path == "/" or path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app.add_middleware(NoCacheFrontendMiddleware)

app.include_router(auth.router)
app.include_router(keys.router)
app.include_router(me.router)
app.include_router(projects.router)
app.include_router(studio_fs.router)
app.include_router(github.router)
app.include_router(billing.router)
app.include_router(models.router)
app.include_router(chat.router)

app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")

# Public demo of Studio workspace landing (no auth) — for shareable links
_COFFEE_DEMO = ROOT / "data" / "workspaces" / "23" / "43" / "src" / "frontend"
if _COFFEE_DEMO.is_dir():
    app.mount(
        "/demo/coffee",
        StaticFiles(directory=str(_COFFEE_DEMO), html=True),
        name="demo_coffee",
    )


@app.get("/")
async def landing():
    return FileResponse(
        FRONTEND / "index.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.get("/app")
async def cabinet():
    return FileResponse(
        FRONTEND / "app.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.get("/health")
async def health():
    return {
        "ok": True,
        "app": settings.APP_NAME,
        "default_model": settings.DEFAULT_MODEL,
        "markup": settings.MARKUP,
        "currency": "RUB",
        "trial_rub": settings.TRIAL_RUB,
    }



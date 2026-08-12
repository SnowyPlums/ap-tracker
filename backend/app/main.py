import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text

from .config import get_settings
from .db import engine
from .routers.auth import router as auth_router
from .routers.rooms import router as rooms_router
from .routers.preferences import router as preferences_router
from .realtime import RoomBroadcaster
from .tracker import TrackerManager
from .routers.live import router as live_router
from .routers.viewer import router as viewer_router
from .retention import retention_loop


broadcaster = RoomBroadcaster()
tracker_manager = TrackerManager(broadcaster)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await tracker_manager.start()
    cleanup_task = asyncio.create_task(retention_loop())
    yield
    cleanup_task.cancel()
    await asyncio.gather(cleanup_task, return_exceptions=True)
    await tracker_manager.stop()
    await engine.dispose()


settings = get_settings()
app = FastAPI(title="Archipelago Tracker API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    https_only=settings.environment == "production",
    same_site="lax",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(rooms_router)
app.include_router(preferences_router)
app.include_router(live_router)
app.include_router(viewer_router)
app.state.broadcaster = broadcaster
app.state.tracker = tracker_manager


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "Archipelago Tracker API",
        "status": "running",
        "health": "/health",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ok"}

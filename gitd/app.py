"""
FastAPI application factory for Ghost in the Droid.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gitd.models.base import Base, engine
from gitd.routers.agent_chat import router as agent_chat_router
from gitd.routers.benchmarks import router as benchmarks_router
from gitd.routers.bot import router as bot_router
from gitd.routers.creator import router as creator_router
from gitd.routers.emulators import pool_router as emulator_pool_router
from gitd.routers.emulators import router as emulators_router
from gitd.routers.explorer import router as explorer_router
from gitd.routers.misc import router as misc_router
from gitd.routers.phone import router as phone_router
from gitd.routers.scheduler import router as scheduler_router
from gitd.routers.skills import router as skills_router
from gitd.routers.streaming import router as streaming_router
from gitd.routers.streaming_viewers import router as streaming_viewers_router
from gitd.routers.tests import router as tests_router
from gitd.routers.tools_hub import router as tools_hub_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    Base.metadata.create_all(bind=engine)
    from gitd.routers.misc import setup_log_capture
    from gitd.services import scheduler_service

    setup_log_capture()
    scheduler_service.start()
    try:
        from gitd.services.device_context import wireless_reconnect_all

        reconnected = wireless_reconnect_all()
        for r in reconnected:
            if r.get("ok"):
                logger.info("Reconnected %s", r["ip"])
    except Exception:
        pass
    yield
    scheduler_service.stop()


TAGS_METADATA = [
    {"name": "phone", "description": "ADB device control, tap, swipe, screenshots"},
    {"name": "streaming", "description": "MJPEG + WebRTC phone screen streaming"},
    {"name": "skills", "description": "Installed skill packages, run actions/workflows"},
    {"name": "creator", "description": "LLM-assisted skill builder with device stream"},
    {"name": "explorer", "description": "Auto app explorer (BFS state discovery)"},
    {"name": "agent-chat", "description": "Natural language phone control via LLM"},
    {"name": "bot", "description": "Bot job queue and manual run"},
    {"name": "scheduler", "description": "Job scheduling, queue management, history"},
    {"name": "tests", "description": "Test runner, recordings, per-device execution"},
    {"name": "stats", "description": "Dashboard stats"},
    {"name": "tools", "description": "Utility tools hub"},
    {"name": "misc", "description": "Health, logs, server management"},
    {"name": "emulators", "description": "Emulator lifecycle, AVDs, snapshots, pool management"},
    {"name": "benchmarks", "description": "Benchmark runner — task suites, live progress, results"},
]


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(
        title="Ghost in the Droid API",
        description="Open-source Android automation — give any AI agent an Android body",
        version="1.0.0",
        lifespan=lifespan,
        openapi_tags=TAGS_METADATA,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Premium tab registry — plugins append to this list
    app.state.premium_tabs = []

    @app.get("/api/health", summary="Health Check")
    def health():
        return {"status": "ok", "server": "fastapi"}

    @app.get("/api/features", summary="Available Features")
    def features():
        """Return available feature tabs. Premium plugins extend this list."""
        return {"premium_tabs": app.state.premium_tabs}

    # Core routers
    app.include_router(misc_router)
    app.include_router(phone_router)
    app.include_router(streaming_router)
    app.include_router(streaming_viewers_router)
    app.include_router(skills_router)
    app.include_router(creator_router)
    app.include_router(explorer_router)
    app.include_router(agent_chat_router)
    app.include_router(tools_hub_router)
    app.include_router(bot_router)
    app.include_router(scheduler_router)
    app.include_router(tests_router)
    app.include_router(emulators_router)
    app.include_router(emulator_pool_router)
    app.include_router(benchmarks_router)

    # Plugin hook: load premium features if installed
    try:
        import ghost_premium

        ghost_premium.register(app)
        logger.info("Premium plugin loaded: %s", ghost_premium.__version__)
    except ImportError:
        pass

    return app


app = create_app()

from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.batch import router as batch_router
from app.api.routers.campagnes import router as campagnes_router
from app.api.routers.cibles import router as cibles_router
from app.api.routers.clients import router as clients_router
from app.api.routers.dashboard import router as dashboard_router
from app.api.routers.data_admin import router as data_admin_router
from app.api.routers.health import router as health_router
from app.api.routers.modeles import router as modeles_router
from app.api.routers.queues import router as queues_router
from app.api.routers.terrain_queues import router as terrain_queues_router
from app.batch.scheduler import start_batch_scheduler, stop_batch_scheduler
from app.orchestration.campaign_worker import start_orchestration_worker, stop_orchestration_worker
from app.outbound.worker import start_outbound_workers, stop_outbound_workers
from app.inbound.worker import start_inbound_workers, stop_inbound_workers
from app.storage.postgres_db import close_pools

API_PREFIX = "/api"

ALLOWED_ORIGINS = [
    "https://marketing-automation.axplitest.com",
    # Anciens frontends conservés temporairement pour compatibilité.
    "https://campain.dev.swiftnova.ma",
    "https://campain.swiftnova.ma",
    # Développement local.
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8081",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cycle de vie API : démarre et arrête le scheduler quotidien."""
    _ = app
    start_batch_scheduler()
    start_orchestration_worker()
    start_outbound_workers()
    start_inbound_workers()

    try:
        yield
    finally:
        stop_inbound_workers()
        stop_outbound_workers()
        stop_orchestration_worker()
        stop_batch_scheduler()
        close_pools()


app = FastAPI(
    title="Marketing Automation API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=API_PREFIX, tags=["Health"])
app.include_router(batch_router, prefix=API_PREFIX, tags=["Batch"])
app.include_router(campagnes_router, prefix=API_PREFIX, tags=["Campagnes"])
app.include_router(modeles_router, prefix=API_PREFIX, tags=["Modeles"])
app.include_router(cibles_router, prefix=API_PREFIX, tags=["Cibles"])
app.include_router(queues_router, prefix=API_PREFIX, tags=["Queues"])
app.include_router(data_admin_router, prefix=API_PREFIX, tags=["Data"])
app.include_router(dashboard_router, prefix=API_PREFIX, tags=["Dashboard"])
app.include_router(clients_router, prefix=API_PREFIX, tags=["Clients"])
app.include_router(
    terrain_queues_router,
    prefix=API_PREFIX,
    tags=["Terrain Queues"],
)

from __future__ import annotations

from fastapi import FastAPI

from app.api.routers.health import router as health_router
from app.api.routers.batch import router as batch_router
from app.api.routers.campagnes import router as campagnes_router
from app.api.routers.modeles import router as modeles_router
from app.api.routers.cibles import router as cibles_router
from app.api.routers.queues import router as queues_router
from app.api.routers.data_admin import router as data_admin_router
from app.api.routers.dashboard import router as dashboard_router
from app.api.routers.clients import router as clients_router

app = FastAPI(
    title="Marketing Automation API",
    version="1.0.0",
)

API_PREFIX = "/api"

ALLOWED_ORIGINS = [
    "https://campain.dev.swiftnova.ma",
    "https://campain.swiftnova.ma",
    "http://localhost:3000",
    "http://localhost:5173",
]


app.include_router(health_router, prefix=API_PREFIX, tags=["Health"])
app.include_router(batch_router, prefix=API_PREFIX, tags=["Batch"])
app.include_router(campagnes_router, prefix=API_PREFIX, tags=["Campagnes"])
app.include_router(modeles_router, prefix=API_PREFIX, tags=["Modeles"])
app.include_router(cibles_router, prefix=API_PREFIX, tags=["Cibles"])
app.include_router(queues_router, prefix=API_PREFIX, tags=["Queues"])
app.include_router(data_admin_router, prefix=API_PREFIX, tags=["Data"])
app.include_router(dashboard_router, prefix=API_PREFIX, tags=["Dashboard"])
app.include_router(clients_router, prefix=API_PREFIX, tags=["Clients"])

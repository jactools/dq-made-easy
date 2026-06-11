from datetime import datetime, timezone

from fastapi import APIRouter

from app.api.v1.schemas import HealthView, ReadinessView
from app.application.resolvers import resolve_health_view, resolve_readiness_view

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthView)
async def health() -> HealthView:
    return resolve_health_view(
        {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


@router.get("/live", response_model=HealthView)
async def live() -> HealthView:
    return await health()


@router.get("/readiness", response_model=ReadinessView)
async def readiness() -> ReadinessView:
    return resolve_readiness_view(
        {
        "status": "ready",
        "checks": {
            "api": "up",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


@router.get("/ready", response_model=ReadinessView)
async def ready() -> ReadinessView:
    return await readiness()

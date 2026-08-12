"""Delivery Registry — Canonical Delivery Registry.

Delivery is a standalone FastAPI app that provides the Canonical Delivery Registry
per the Solution Design: Canonical Data Delivery Phase 1.

Delivery can be:
1. Run as a standalone app (uvicorn delivery.main:app)
2. Mounted as a sub-app in another FastAPI app (app.mount("/delivery", delivery_app))

All Delivery endpoints are prefixed with /v1/.
"""

from __future__ import annotations

from fastapi import FastAPI

from delivery.endpoints.deliveries import router as deliveries_router
from delivery.endpoints.dq_results import router as dq_results_router

app = FastAPI(
    title="Delivery — Canonical Delivery Registry",
    description="Enterprise Metadata Repository for canonical delivery tracking.",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Mount endpoints under /v1/
v1_router = FastAPI()
v1_router.include_router(deliveries_router)
v1_router.include_router(dq_results_router)
app.mount("/v1", v1_router)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "service": "delivery"}


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "service": "Delivery — Canonical Delivery Registry",
        "version": "0.1.0",
        "docs": "/docs",
        "api_prefix": "/v1",
    }


def get_app() -> FastAPI:
    """Factory function to create the Delivery app.

    This allows the app to be imported and mounted as a sub-app.
    """
    return app

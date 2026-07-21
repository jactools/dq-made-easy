"""EMR (Enterprise Metadata Repository) — Canonical Delivery Registry.

EMR is a standalone FastAPI app that provides the Canonical Delivery Registry
per the Solution Design: Canonical Data Delivery Phase 1.

EMR can be:
1. Run as a standalone app (uvicorn emr.main:app)
2. Mounted as a sub-app in another FastAPI app (app.mount("/emr", emr_app))

All EMR endpoints are prefixed with /v1/.
"""

from __future__ import annotations

from fastapi import FastAPI

from emr.endpoints.deliveries import router as deliveries_router

app = FastAPI(
    title="EMR — Canonical Delivery Registry",
    description="Enterprise Metadata Repository for canonical delivery tracking.",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Mount delivery endpoints under /v1/
v1_router = FastAPI()
v1_router.include_router(deliveries_router)
app.mount("/v1", v1_router)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "service": "emr"}


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "service": "EMR — Canonical Delivery Registry",
        "version": "0.1.0",
        "docs": "/docs",
        "api_prefix": "/v1",
    }


def get_app() -> FastAPI:
    """Factory function to create the EMR app.

    This allows the app to be imported and mounted as a sub-app.
    """
    return app

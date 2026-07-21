from contextlib import asynccontextmanager
import inspect
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import Response
from pathlib import Path

from app.api.v1.router import api_router
from app.api.v1.router import internal_api_router
from emr.main import get_app as get_emr_app
from app.core.api_metrics import api_metrics_store, render_prometheus_metrics
from app.core.auth_login_metrics import auth_login_metrics_store, render_prometheus_metrics as render_auth_login_prometheus_metrics
from app.core.config import get_settings
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_admin_repository
from app.core.dependencies import bootstrap_connector_registry
from app.core.jit_access_metrics import render_prometheus_metrics as render_jit_access_request_prometheus_metrics
from app.core.jit_access_metrics import summarize_jit_access_requests
from app.core.errors import register_exception_handlers
from app.core.logging_config import configure_logging
from app.core.runtime_paths import find_runtime_root
from app.core.telemetry import instrument_app, shutdown_telemetry
from app.application.services.natural_language_draft_enqueue_service import _resolve_redis_url as _resolve_natural_language_draft_redis_url
from app.core.runtime_queues import resolve_natural_language_draft_queue_key
from app.application.services.natural_language_draft_queue_worker import build_natural_language_draft_queue_worker
from app.application.services.status_governance_policy_loader import set_status_model_policy_from_source
from app.middleware.api_case_enforcement import ApiCaseEnforcementMiddleware
from app.middleware.auth_middleware import AuthMiddleware
from app.middleware.correlation_id import CorrelationIdMiddleware
from app.middleware.internal_api_contract_validation import InternalApiContractValidationMiddleware
from app.middleware.require_kong_gateway import RequireKongGatewayMiddleware
from app.middleware.timing import RequestTimingMiddleware


_PROOF_CONTRACT_METADATA = {
    "name": "test-proof-payload",
    "version": "v1",
    "schema": "docs/contracts/test-proof-payload/v1/schema.json",
    "example": "docs/contracts/test-proof-payload/v1/example.json",
    "openapi": "docs/contracts/test-proof-payload/v1/openapi.yaml",
    "readme": "docs/contracts/test-proof-payload/README.md",
    "description": "Canonical proof submission contract for POST /api/rulebuilder/v1/rules/{rule_id}/test",
}

_INTERNAL_API_CONTRACTS_INDEX = Path("docs") / "contracts" / "internal-api" / "index.json"
_REPO_ROOT = find_runtime_root(Path(__file__), _INTERNAL_API_CONTRACTS_INDEX)
_INTERNAL_API_CONTRACTS_ROOT = _REPO_ROOT / _INTERNAL_API_CONTRACTS_INDEX.parent


def _build_openapi_schema(app: FastAPI) -> dict:
    schema = get_openapi(
        title=app.title,
        version=app.version,
        summary=app.summary,
        description=app.description,
        routes=app.routes,
    )
    schema["externalDocs"] = {
        "description": "Proof submission contract",
        "url": _PROOF_CONTRACT_METADATA["readme"],
    }
    schema["x-contracts"] = [_PROOF_CONTRACT_METADATA]
    return schema


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    settings.validate_runtime_requirements()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        set_status_model_policy_from_source(get_app_config_repository().get_app_config())
        bootstrap_connector_registry()
        draft_queue_worker = None
        draft_queue_key = resolve_natural_language_draft_queue_key()
        if draft_queue_key:
            redis_url = _resolve_natural_language_draft_redis_url(settings)
            if not redis_url:
                raise RuntimeError("NATURAL_LANGUAGE_DRAFT_QUEUE_KEY is set but Redis is not configured for draft queue processing")
            draft_queue_worker = build_natural_language_draft_queue_worker(
                queue_key=draft_queue_key,
                redis_url=redis_url,
                llm_service_url=settings.llm_service_url,
            )
            draft_queue_worker.start()
        try:
            yield
        finally:
            if draft_queue_worker is not None:
                draft_queue_worker.stop()
            shutdown_result = shutdown_telemetry()
            if inspect.isawaitable(shutdown_result):
                await shutdown_result

    app = FastAPI(
        title=settings.app_name,
        version="0.6.2",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        app.openapi_schema = _build_openapi_schema(app)
        return app.openapi_schema

    app.openapi = custom_openapi

    @app.get("/health", include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        summary = api_metrics_store.get_summary(exclude_health_endpoints=True)
        auth_summary = auth_login_metrics_store.get_summary()
        app_config = get_app_config_repository().get_app_config()
        jit_access_requests = get_admin_repository().list_exception_fact_access_requests(
            request_timeout_minutes=max(1, int(app_config.exceptionFactJitRequestTimeoutMinutes)),
        )
        jit_access_summary = summarize_jit_access_requests(jit_access_requests)
        return Response(
            content="\n".join(
                [
                    render_prometheus_metrics(summary).rstrip("\n"),
                    render_auth_login_prometheus_metrics(auth_summary).rstrip("\n"),
                    render_jit_access_request_prometheus_metrics(jit_access_summary).rstrip("\n"),
                    "",
                ]
            ),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID", "X-Process-Time-MS", "X-Trace-ID"],
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(RequireKongGatewayMiddleware)
    app.add_middleware(InternalApiContractValidationMiddleware, contracts_root=_INTERNAL_API_CONTRACTS_ROOT)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(ApiCaseEnforcementMiddleware)
    # Ensure timing/metrics wrap the full middleware chain so we still
    # capture request metrics when inner middleware returns early (e.g. auth).
    app.add_middleware(RequestTimingMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.include_router(internal_api_router, prefix=settings.api_v1_prefix)
    app.include_router(api_router, prefix=settings.gateway_api_prefix, include_in_schema=False)

    # Mount EMR as a standalone sub-app under /emr/
    emr_app = get_emr_app()
    app.mount("/emr", emr_app)

    instrument_app(app, settings)

    return app


app = create_app()

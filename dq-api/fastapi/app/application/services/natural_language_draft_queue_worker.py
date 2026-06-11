from __future__ import annotations

import asyncio
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC, datetime
import json
import logging
from threading import Event, Thread

from app.application.services.data_definition_task_service import ANALYSIS_TYPE_DEFINITION_TASK
from app.application.services.data_definition_task_service import build_data_definition_generation_request
from app.application.services.data_definition_task_service import DataDefinitionTaskError
from app.application.services.data_definition_task_service import fetch_data_definition_bundle
from app.application.services.data_definition_task_service import merge_import_result
from app.application.services.data_definition_task_service import require_approved_openmetadata_import_contract
from app.application.services.natural_language_draft_enqueue_service import load_request_record
from app.application.services.natural_language_draft_enqueue_service import mark_request_completed
from app.application.services.natural_language_draft_enqueue_service import mark_request_started
from app.application.services.natural_language_rule_drafting import build_natural_language_rule_draft_suggestion_payload
from app.application.services.natural_language_rule_drafting import build_natural_language_rule_preview_payload_for_provider
from app.application.services.openmetadata_definition_importer import OpenMetadataDefinitionImportError
from app.application.services.openmetadata_definition_importer import OpenMetadataDefinitionImporter
from app.core.config import get_settings
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_suggestions_repository
from app.core.otel_metrics import record_natural_language_draft_request_event
from app.core.otel_metrics import record_suggestions_redis_failure
from app.core.otel_metrics import record_suggestions_redis_request

try:
    import redis
except Exception:
    redis = None


@dataclass(slots=True)
class NaturalLanguageDraftQueueWorker:
    queue_key: str
    redis_url: str
    llm_service_url: str
    stop_event: Event
    _thread: Thread = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._thread = Thread(target=self._run, name="natural-language-draft-worker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        logger = logging.getLogger("app.application.services.natural_language_draft_queue_worker")
        if redis is None:
            logger.error("redis package is not installed; natural-language draft worker cannot start")
            return

        client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        suggestions_repository = get_suggestions_repository()
        catalog_repository = get_data_catalog_repository()
        settings = get_settings()
        importer = OpenMetadataDefinitionImporter(
            provider=settings.catalog_provider,
            endpoint=settings.catalog_endpoint,
            api_key=settings.catalog_api_key,
            oidc_issuer=settings.catalog_oidc_issuer,
            oidc_token_url=settings.catalog_oidc_token_url,
            oidc_client_id=settings.catalog_oidc_client_id,
            oidc_client_secret=settings.catalog_oidc_client_secret,
            oidc_scope=settings.catalog_oidc_scope,
            oidc_username=settings.catalog_oidc_username,
            oidc_password=settings.catalog_oidc_password,
            timeout_seconds=settings.catalog_timeout_seconds,
        )

        while not self.stop_event.is_set():
            try:
                item = client.brpop(self.queue_key, timeout=1)
            except Exception as exc:
                record_suggestions_redis_failure(operation_type="brpop", failure_type=exc.__class__.__name__)
                raise
            record_suggestions_redis_request(operation_type="brpop", status="success")
            if not item:
                continue

            _, payload_raw = item
            try:
                payload = json.loads(payload_raw)
            except Exception:
                logger.exception("failed to parse natural-language draft queue payload")
                continue

            request_id = str(payload.get("request_id") or "").strip()
            job_id = str(payload.get("job_id") or request_id).strip() or request_id
            analysis_provider = str(payload.get("analysis_provider") or "unknown").strip().lower() or "unknown"
            if not request_id:
                logger.error("received natural-language draft job without request_id")
                record_natural_language_draft_request_event(
                    stage="worker",
                    result="failure",
                    analysis_provider=analysis_provider,
                    error_code="missing_request_id",
                )
                continue

            if load_request_record(client, request_id) is None:
                logger.error("natural-language draft request %s is missing from Redis", request_id)
                record_natural_language_draft_request_event(
                    stage="worker",
                    result="failure",
                    analysis_provider=analysis_provider,
                    error_code="request_not_found",
                )
                try:
                    suggestions_repository.update_natural_language_request(
                        request_id=request_id,
                        status="failed",
                        job_id=job_id,
                        completed_at=_current_timestamp(),
                        error_message="Natural-language draft request is missing from Redis",
                    )
                except Exception:
                    logger.exception("failed to update missing natural-language request state", extra={"request_id": request_id, "job_id": job_id})
                continue

            try:
                mark_request_started(client, request_id=request_id, job_id=job_id)
                try:
                    suggestions_repository.update_natural_language_request(
                        request_id=request_id,
                        status="started",
                        job_id=job_id,
                        started_at=_current_timestamp(),
                    )
                except Exception:
                    logger.exception("failed to update natural-language request start state", extra={"request_id": request_id, "job_id": job_id})
                analysis_type = str(payload.get("analysis_type") or "preview").strip().lower() or "preview"
                if analysis_type == ANALYSIS_TYPE_DEFINITION_TASK:
                    task_payload = payload.get("task_payload") if isinstance(payload.get("task_payload"), dict) else {}
                    llm_request_payload = build_data_definition_generation_request(
                        task_payload={
                            **task_payload,
                            "request_id": request_id,
                            "current_workspace_id": str(payload.get("current_workspace_id") or ""),
                            "version_id": str(payload.get("version_id") or ""),
                            "selected_attribute_ids": list(payload.get("selected_attribute_ids") or []),
                        },
                        catalog_repository=catalog_repository,
                    )
                    result_payload = asyncio.run(
                        fetch_data_definition_bundle(
                            request_payload=llm_request_payload,
                            llm_service_url=self.llm_service_url,
                        )
                    )

                    if bool(payload.get("auto_import")):
                        import_contract = require_approved_openmetadata_import_contract(result=result_payload)
                        try:
                            import_report = importer.import_contract(import_contract)
                        except OpenMetadataDefinitionImportError as exc:
                            raise DataDefinitionTaskError(str(exc), status_code=exc.status_code) from exc
                        result_payload = merge_import_result(result=result_payload, import_report=import_report)

                    mark_request_completed(
                        client,
                        request_id=request_id,
                        success=True,
                        result=result_payload,
                    )
                    try:
                        suggestions_repository.update_natural_language_request(
                            request_id=request_id,
                            status="completed",
                            job_id=job_id,
                            completed_at=_current_timestamp(),
                            result=result_payload,
                        )
                    except Exception:
                        logger.exception("failed to update data-definition task completion", extra={"request_id": request_id, "job_id": job_id})
                    record_natural_language_draft_request_event(
                        stage="worker",
                        result="success",
                        analysis_provider=analysis_provider,
                    )
                    logger.info("completed data-definition task request %s", request_id)
                    continue

                preview_payload = asyncio.run(
                    build_natural_language_rule_preview_payload_for_provider(
                        prompt=str(payload.get("prompt") or ""),
                        search_scope=str(payload.get("search_scope") or "current"),
                        current_workspace_id=str(payload.get("current_workspace_id") or ""),
                        accessible_workspace_ids={str(item).strip() for item in list(payload.get("accessible_workspace_ids") or []) if str(item).strip()},
                        catalog_repository=catalog_repository,
                        analysis_provider=str(payload.get("analysis_provider") or "llm"),
                        llm_service_url=self.llm_service_url,
                    )
                )

                selected_attribute_ids = [str(item or "").strip() for item in list(payload.get("selected_attribute_ids") or []) if str(item or "").strip()]
                if not selected_attribute_ids:
                    mark_request_completed(
                        client,
                        request_id=request_id,
                        success=True,
                        result=preview_payload,
                    )
                    try:
                        suggestions_repository.update_natural_language_request(
                            request_id=request_id,
                            status="completed",
                            job_id=job_id,
                            completed_at=_current_timestamp(),
                            result=preview_payload,
                        )
                    except Exception:
                        logger.exception("failed to update natural-language preview completion", extra={"request_id": request_id, "job_id": job_id})
                    record_natural_language_draft_request_event(
                        stage="worker",
                        result="success",
                        analysis_provider=analysis_provider,
                    )
                    logger.info("completed natural-language preview request %s", request_id)
                    continue

                candidate_ids = {
                    str(candidate.get("attribute_id") or "").strip()
                    for candidate in list(preview_payload.get("candidate_attributes") or [])
                    if str(candidate.get("attribute_id") or "").strip()
                }
                if not selected_attribute_ids:
                    raise ValueError("Select at least one candidate attribute before creating a draft suggestion.")
                if any(selected_id not in candidate_ids for selected_id in selected_attribute_ids):
                    raise ValueError("One or more selected attributes are no longer valid for this preview scope.")

                draft_payload = build_natural_language_rule_draft_suggestion_payload(
                    prompt=str(payload.get("prompt") or ""),
                    search_scope=str(payload.get("search_scope") or "current"),
                    current_workspace_id=str(payload.get("current_workspace_id") or ""),
                    selected_attribute_ids=selected_attribute_ids,
                    preview_payload=preview_payload,
                )

                created = suggestions_repository.create_suggestion(
                    user_id=str(payload.get("requested_by_user_id") or ""),
                    data_source_id=str(draft_payload["data_source_id"]),
                    suggested_rule=draft_payload["suggested_rule"],
                    confidence_score=draft_payload["confidence_score"],
                    reason=draft_payload["reason"],
                    rule_type=draft_payload["rule_type"],
                )

                mark_request_completed(
                    client,
                    request_id=request_id,
                    success=True,
                    suggestion_id=created.id,
                    result={"suggestion_id": created.id},
                )
                try:
                    suggestions_repository.update_natural_language_request(
                        request_id=request_id,
                        status="completed",
                        job_id=job_id,
                        completed_at=_current_timestamp(),
                        suggestion_id=created.id,
                        result={"suggestion_id": created.id},
                    )
                except Exception:
                    logger.exception("failed to update natural-language draft completion", extra={"request_id": request_id, "job_id": job_id})
                record_natural_language_draft_request_event(
                    stage="worker",
                    result="success",
                    analysis_provider=analysis_provider,
                )
                logger.info("completed natural-language draft request %s", request_id)
            except Exception as exc:
                logger.exception("natural-language draft request %s failed", request_id)
                try:
                    suggestions_repository.update_natural_language_request(
                        request_id=request_id,
                        status="failed",
                        job_id=job_id,
                        completed_at=_current_timestamp(),
                        error_message=str(exc),
                    )
                except Exception:
                    logger.exception("failed to update natural-language request failure state", extra={"request_id": request_id, "job_id": job_id})
                record_natural_language_draft_request_event(
                    stage="worker",
                    result="failure",
                    analysis_provider=analysis_provider,
                    error_code="worker_failure",
                )
                mark_request_completed(client, request_id=request_id, success=False, error_message=str(exc))


def _current_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def build_natural_language_draft_queue_worker(*, queue_key: str, redis_url: str, llm_service_url: str) -> NaturalLanguageDraftQueueWorker:
    return NaturalLanguageDraftQueueWorker(
        queue_key=queue_key,
        redis_url=redis_url,
        llm_service_url=llm_service_url,
        stop_event=Event(),
    )
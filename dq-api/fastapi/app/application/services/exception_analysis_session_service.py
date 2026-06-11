from __future__ import annotations

import asyncio
import gzip
import hashlib
import math
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from app.application.services.exception_storage import ExceptionStorageError
from app.domain.interfaces import ExceptionAnalysisSessionRepository
from app.domain.interfaces import ExceptionFactRepository


class ExceptionAnalysisSliceStorageBackend(Protocol):
    async def persist_analysis_pack(
        self,
        payload: Mapping[str, object],
        *,
        analysis_session_id: str,
        analysis_slice_id: str,
        data_object_version_id: str,
        execution_run_id: str,
        rule_id: str,
    ) -> dict[str, str]:
        ...

    async def load_analysis_pack(self, analysis_pack_uri: str) -> dict[str, object]:
        ...


class S3ExceptionAnalysisSliceStorageBackend(ExceptionAnalysisSliceStorageBackend):
    def __init__(
        self,
        *,
        bucket: str,
        prefix: str,
        endpoint: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        ssl_enabled: bool = True,
        client_factory: Any | None = None,
    ) -> None:
        from app.application.services.exception_storage import S3ExceptionStorageBackend

        self._backend = S3ExceptionStorageBackend(
            bucket=bucket,
            prefix=prefix,
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            region=region,
            ssl_enabled=ssl_enabled,
            client_factory=client_factory,
        )

    async def persist_analysis_pack(
        self,
        payload: Mapping[str, object],
        *,
        analysis_session_id: str,
        analysis_slice_id: str,
        data_object_version_id: str,
        execution_run_id: str,
        rule_id: str,
    ) -> dict[str, str]:
        analysis_pack_uri, analysis_pack_sha256 = await self._put_gzipped_json_object(
            payload,
            analysis_session_id=analysis_session_id,
            analysis_slice_id=analysis_slice_id,
            data_object_version_id=data_object_version_id,
            execution_run_id=execution_run_id,
            rule_id=rule_id,
            object_name=f"analysis-pack-",
            storage_kind="gx_analysis_slice_pack",
        )

        manifest_payload = self._build_manifest_payload(
            payload,
            analysis_pack_uri=analysis_pack_uri,
            analysis_pack_sha256=analysis_pack_sha256,
        )
        analysis_manifest_uri, analysis_manifest_sha256 = await self._put_gzipped_json_object(
            manifest_payload,
            analysis_session_id=analysis_session_id,
            analysis_slice_id=analysis_slice_id,
            data_object_version_id=data_object_version_id,
            execution_run_id=execution_run_id,
            rule_id=rule_id,
            object_name=f"analysis-manifest-",
            storage_kind="gx_analysis_slice_manifest",
        )

        return {
            "analysisPackUri": analysis_pack_uri,
            "analysisPackSha256": analysis_pack_sha256,
            "analysisManifestUri": analysis_manifest_uri,
            "analysisManifestSha256": analysis_manifest_sha256,
        }

    @staticmethod
    def _build_manifest_payload(
        payload: Mapping[str, object],
        *,
        analysis_pack_uri: str,
        analysis_pack_sha256: str,
    ) -> dict[str, object]:
        manifest_payload = {key: value for key, value in dict(payload).items() if key != "records"}
        manifest_payload.update(
            {
                "manifestVersion": "v1",
                "analysisPackUri": analysis_pack_uri,
                "analysisPackSha256": analysis_pack_sha256,
            }
        )
        return manifest_payload

    async def _put_gzipped_json_object(
        self,
        payload: Mapping[str, object],
        *,
        analysis_session_id: str,
        analysis_slice_id: str,
        data_object_version_id: str,
        execution_run_id: str,
        rule_id: str,
        object_name: str,
        storage_kind: str,
    ) -> tuple[str, str]:
        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        content_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        object_key = "/".join(
            part
            for part in [
                self._backend._prefix or "gx-analysis-slices",
                f"analysis_session_id={analysis_session_id}",
                f"analysis_slice_id={analysis_slice_id}",
                f"data_object_version_id={data_object_version_id}",
                f"execution_run_id={execution_run_id}",
                f"rule_id={rule_id}",
                f"{object_name}{content_hash}.json.gz",
            ]
            if part
        )
        compressed_body = gzip.compress(canonical_json.encode("utf-8"))
        await asyncio.to_thread(
            self._backend._client.put_object,
            Bucket=self._backend._bucket,
            Key=object_key,
            Body=compressed_body,
            ContentType="application/json",
            ContentEncoding="gzip",
            Metadata={
                "content_sha256": content_hash,
                "storage_kind": storage_kind,
                "analysis_session_id": analysis_session_id,
                "analysis_slice_id": analysis_slice_id,
                "data_object_version_id": data_object_version_id,
                "execution_run_id": execution_run_id,
                "rule_id": rule_id,
            },
        )
        return f"s3://{self._backend._bucket}/{object_key}", content_hash

    async def load_analysis_pack(self, analysis_pack_uri: str) -> dict[str, object]:
        bucket, key = _split_s3_uri(analysis_pack_uri)
        response = await asyncio.to_thread(self._backend._client.get_object, Bucket=bucket, Key=key)
        body = response["Body"].read()
        try:
            raw = gzip.decompress(body).decode("utf-8")
        except OSError:
            raw = body.decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ExceptionStorageError("Analysis pack storage payload is invalid")
        return payload


def build_exception_analysis_slice_storage_backend(*, settings) -> ExceptionAnalysisSliceStorageBackend:
    endpoint = str(getattr(settings, "gx_exception_storage_endpoint", "") or "").strip()
    bucket = str(getattr(settings, "gx_exception_storage_bucket", "dq-gx-exceptions") or "dq-gx-exceptions").strip() or "dq-gx-exceptions"
    access_key = str(getattr(settings, "gx_exception_storage_access_key", "") or "").strip()
    secret_key = str(getattr(settings, "gx_exception_storage_secret_key", "") or "").strip()
    region = str(getattr(settings, "gx_exception_storage_region", "us-east-1") or "us-east-1").strip() or "us-east-1"
    prefix = str(getattr(settings, "gx_exception_storage_prefix", "gx-analysis-slices") or "gx-analysis-slices").strip() or "gx-analysis-slices"
    ssl_enabled = bool(getattr(settings, "gx_exception_storage_ssl_enabled", True))

    if not endpoint or not access_key or not secret_key:
        raise ExceptionStorageError(
            "GX analysis slice storage requires GX_EXCEPTION_STORAGE_ENDPOINT, GX_EXCEPTION_STORAGE_ACCESS_KEY, and GX_EXCEPTION_STORAGE_SECRET_KEY",
            status_code=503,
        )

    return S3ExceptionAnalysisSliceStorageBackend(
        bucket=bucket,
        prefix=prefix,
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        region=region,
        ssl_enabled=ssl_enabled,
    )


def _split_s3_uri(uri: str) -> tuple[str, str]:
    normalized = str(uri or "").strip()
    if not normalized.startswith("s3://"):
        raise ExceptionStorageError("Analysis pack uri must be an s3:// URI")
    bucket_and_key = normalized.removeprefix("s3://")
    bucket, _, key = bucket_and_key.partition("/")
    if not bucket or not key:
        raise ExceptionStorageError("Analysis pack uri is missing bucket or key")
    return bucket, key


class ExceptionAnalysisSessionService:
    def __init__(
        self,
        *,
        violation_repository: ExceptionFactRepository,
        session_repository: ExceptionAnalysisSessionRepository,
        storage_backend: ExceptionAnalysisSliceStorageBackend,
        max_slice_limit: int = 200,
        analysis_query_limit: int = 5000,
    ) -> None:
        self._violation_repository = violation_repository
        self._session_repository = session_repository
        self._storage_backend = storage_backend
        self._max_slice_limit = max(int(max_slice_limit), 1)
        self._analysis_query_limit = max(int(analysis_query_limit), self._max_slice_limit)

    async def create_session(self, request: Mapping[str, object], *, analysis_session_id: str | None = None) -> dict[str, object]:
        normalized_request = self._normalize_request(request)
        session_id = str(analysis_session_id or uuid4().hex)
        existing_slices = await self._session_repository.list_slices(session_id)
        if existing_slices and not self._has_explicit_filters(normalized_request):
            normalized_request = self._seed_request_from_session(existing_slices[-1], normalized_request)
        slice_index = (max((int(row.get("sliceIndex") or 0) for row in existing_slices), default=0) + 1) if existing_slices else 1
        started_at = datetime.now(UTC)
        current_payload = await self._create_slice(session_id=session_id, slice_index=slice_index, request=normalized_request)
        if not bool(normalized_request.get("runUntilExhausted") or False):
            return {
                **current_payload,
                "analysisStatus": self._build_analysis_status(
                    slices=current_payload.get("slices") or [],
                    current_slice=current_payload.get("currentSlice") or {},
                    state="in_progress",
                    reason="The analysis session created a single slice and is ready for the next slice.",
                    max_slices=normalized_request.get("maxSlices") if isinstance(normalized_request.get("maxSlices"), int) else None,
                    max_records=normalized_request.get("maxRecords") if isinstance(normalized_request.get("maxRecords"), int) else None,
                    max_seconds=normalized_request.get("maxSeconds") if isinstance(normalized_request.get("maxSeconds"), int) else None,
                ),
            }

        return await self._continue_session_until_budget_or_exhausted(
            session_id=session_id,
            slice_index=slice_index,
            request=normalized_request,
            current_payload=current_payload,
            started_at=started_at,
            existing_slices=existing_slices,
        )

    async def get_session(self, analysis_session_id: str) -> dict[str, object] | None:
        slices = await self._session_repository.list_slices(analysis_session_id)
        if not slices:
            return None

        current_row = max(slices, key=lambda item: (int(item.get("sliceIndex") or 0), str(item.get("analysisSliceId") or "")))
        current_slice = await self._build_slice_response(current_row, summary_only=False)
        summaries = [self._build_slice_summary(row) for row in slices]
        return await self._build_session_payload(
            slices=summaries,
            current_slice=current_slice,
            analysis_status=self._build_analysis_status(slices=summaries, current_slice=current_slice),
        )

    async def get_session_summary(self, analysis_session_id: str) -> dict[str, object] | None:
        slices = await self._session_repository.list_slices(analysis_session_id)
        if not slices:
            return None

        current_row = max(slices, key=lambda item: (int(item.get("sliceIndex") or 0), str(item.get("analysisSliceId") or "")))
        current_slice = await self._build_slice_response(current_row, summary_only=True)
        summaries = [self._build_slice_summary(row) for row in slices]
        return await self._build_session_payload(
            slices=summaries,
            current_slice=current_slice,
            analysis_status=self._build_analysis_status(slices=summaries, current_slice=current_slice),
        )

    async def get_slice(self, analysis_session_id: str, analysis_slice_id: str) -> dict[str, object] | None:
        row = await self._session_repository.get_slice(analysis_session_id, analysis_slice_id)
        if row is None:
            return None
        payload = await self._build_slice_detail(row)
        return {**payload, "analysisStatus": self._build_analysis_status(slices=[self._build_slice_summary(row)], current_slice=payload)}

    async def _create_slice(self, *, session_id: str, slice_index: int, request: Mapping[str, object]) -> dict[str, object]:
        anchor_rows = await self._violation_repository.list_violations(
            data_object_version_id=str(request["dataObjectVersionId"]),
            execution_run_id=str(request["executionRunId"]),
            rule_id=str(request["ruleId"]),
            limit=self._analysis_query_limit,
            offset=0,
        )
        filtered_rows = await self._violation_repository.list_violations(
            data_object_version_id=str(request["dataObjectVersionId"]),
            execution_run_id=str(request["executionRunId"]),
            rule_id=str(request["ruleId"]),
            reason_codes=list(request.get("reasonCodes") or []),
            failure_class=request.get("failureClass") if isinstance(request.get("failureClass"), str) else None,
            record_identifier_type=request.get("recordIdentifierType") if isinstance(request.get("recordIdentifierType"), str) else None,
            record_identifier_value_contains=request.get("recordIdentifierValueContains") if isinstance(request.get("recordIdentifierValueContains"), str) else None,
            search=request.get("search") if isinstance(request.get("search"), str) else None,
            detected_after=request.get("detectedAfter") if isinstance(request.get("detectedAfter"), str) else None,
            detected_before=request.get("detectedBefore") if isinstance(request.get("detectedBefore"), str) else None,
            hash_stripe=request.get("hashStripe") if isinstance(request.get("hashStripe"), int) else None,
            hash_stripe_count=request.get("hashStripeCount") if isinstance(request.get("hashStripeCount"), int) else None,
            limit=self._analysis_query_limit,
            offset=0,
        )

        anchor_records = [row.model_dump(mode="python", by_alias=False) for row in anchor_rows.data]
        filtered_records = [row.model_dump(mode="python", by_alias=False) for row in filtered_rows.data[: min(int(request["sliceLimit"]), self._max_slice_limit)]]
        filtered_record_ids = {str(row.get("id") or "") for row in filtered_records}
        uncovered_records = [row for row in anchor_records if str(row.get("id") or "") not in filtered_record_ids]
        suggestion = self._build_next_slice_suggestion(request, uncovered_records)

        now = datetime.now(UTC).isoformat()
        payload = {
            "analysisSessionId": session_id,
            "analysisSliceId": f"slice-{uuid4().hex}",
            "sliceIndex": slice_index,
            "dataObjectVersionId": str(request["dataObjectVersionId"]),
            "executionRunId": str(request["executionRunId"]),
            "ruleId": str(request["ruleId"]),
            "sliceLimit": int(request["sliceLimit"]),
            "anchorTotalCount": int(anchor_rows.total),
            "totalMatchingCount": int(filtered_rows.total),
            "returnedCount": len(filtered_records),
            "truncated": int(filtered_rows.total) > len(filtered_records),
            "filters": {
                "dataObjectVersionId": str(request["dataObjectVersionId"]),
                "executionRunId": str(request["executionRunId"]),
                "ruleId": str(request["ruleId"]),
                "reasonCodes": list(request.get("reasonCodes") or []),
                "failureClass": request.get("failureClass"),
                "recordIdentifierType": request.get("recordIdentifierType"),
                "recordIdentifierValueContains": request.get("recordIdentifierValueContains"),
                "search": request.get("search"),
                "detectedAfter": request.get("detectedAfter"),
                "detectedBefore": request.get("detectedBefore"),
                "hashStripe": request.get("hashStripe"),
                "hashStripeCount": request.get("hashStripeCount"),
                "sliceLimit": int(request["sliceLimit"]),
                "runUntilExhausted": bool(request.get("runUntilExhausted") or False),
                "maxSlices": request.get("maxSlices"),
                "maxRecords": request.get("maxRecords"),
                "maxSeconds": request.get("maxSeconds"),
            },
            "records": filtered_records,
            "nextSliceSuggestion": suggestion,
            "createdAt": now,
            "updatedAt": now,
        }
        artifact_locations = await self._storage_backend.persist_analysis_pack(
            payload,
            analysis_session_id=session_id,
            analysis_slice_id=str(payload["analysisSliceId"]),
            data_object_version_id=str(request["dataObjectVersionId"]),
            execution_run_id=str(request["executionRunId"]),
            rule_id=str(request["ruleId"]),
        )
        analysis_pack_uri = str(artifact_locations["analysisPackUri"])
        analysis_pack_sha256 = str(artifact_locations["analysisPackSha256"])
        analysis_manifest_uri = str(artifact_locations["analysisManifestUri"])
        analysis_manifest_sha256 = str(artifact_locations["analysisManifestSha256"])
        row_payload = {
            **payload,
            "analysisPackUri": analysis_pack_uri,
            "analysisPackSha256": analysis_pack_sha256,
            "analysisManifestUri": analysis_manifest_uri,
            "analysisManifestSha256": analysis_manifest_sha256,
        }
        await self._session_repository.save_slice(row_payload)
        stored_slices = await self._session_repository.list_slices(session_id)
        current_row = stored_slices[-1] if stored_slices else row_payload
        current_slice = await self._build_slice_response(current_row, summary_only=bool(request.get("summaryOnly") or False))
        return await self._build_session_payload(
            slices=stored_slices or [self._build_slice_summary(row_payload)],
            current_slice=current_slice,
        )

    async def _continue_session_until_budget_or_exhausted(
        self,
        *,
        session_id: str,
        slice_index: int,
        request: Mapping[str, object],
        current_payload: Mapping[str, object],
        started_at: datetime,
        existing_slices: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        working_request = dict(request)
        seen_signatures = {self._request_signature(working_request)}
        current_slice_index = slice_index
        exhausted = False
        stalled = False
        budget_hit = False
        status_reason = "Analysis session is in progress."

        historical_slice_count = len(existing_slices)
        historical_record_count = sum(int(row.get("returnedCount") or 0) for row in existing_slices)

        while True:
            suggestion = current_payload.get("currentSlice", {}).get("nextSliceSuggestion") if isinstance(current_payload.get("currentSlice"), Mapping) else None
            if not isinstance(suggestion, Mapping):
                stalled = True
                status_reason = "The current slice did not produce a follow-up suggestion."
                break

            remaining_count = int(suggestion.get("remainingCount") or 0)
            if remaining_count <= 0:
                exhausted = True
                status_reason = "The analysis session exhausted the uncovered exception space."
                break

            max_slices = working_request.get("maxSlices")
            if isinstance(max_slices, int) and max_slices > 0 and (historical_slice_count + int(current_payload.get("sliceCount") or 0)) >= max_slices:
                budget_hit = True
                status_reason = "Stopped after reaching the configured slice budget."
                break

            max_records = working_request.get("maxRecords")
            current_record_count = historical_record_count + sum(
                int(row.get("returnedCount") or 0)
                for row in (current_payload.get("slices") or [])
                if isinstance(row, Mapping)
            )
            if isinstance(max_records, int) and max_records > 0 and current_record_count >= max_records:
                budget_hit = True
                status_reason = "Stopped after reaching the configured record budget."
                break

            max_seconds = working_request.get("maxSeconds")
            elapsed_seconds = (datetime.now(UTC) - started_at).total_seconds()
            if isinstance(max_seconds, int) and max_seconds > 0 and elapsed_seconds >= max_seconds:
                budget_hit = True
                status_reason = "Stopped after reaching the configured time budget."
                break

            next_request = self._build_request_from_suggestion(working_request, suggestion)
            next_signature = self._request_signature(next_request)
            if next_signature in seen_signatures:
                stalled = True
                status_reason = "The partition strategy repeated an already executed filter set."
                break

            seen_signatures.add(next_signature)
            working_request = next_request
            current_slice_index += 1
            current_payload = await self._create_slice(session_id=session_id, slice_index=current_slice_index, request=working_request)

        return await self._build_session_payload(
            slices=current_payload.get("slices") or [],
            current_slice=current_payload.get("currentSlice") or {},
            analysis_status=self._build_analysis_status(
                slices=current_payload.get("slices") or [],
                current_slice=current_payload.get("currentSlice") or {},
                state="complete" if exhausted else "budget_hit" if budget_hit else "stalled" if stalled else "in_progress",
                reason=status_reason,
                exhausted=exhausted,
                budget_hit=budget_hit,
                stalled=stalled,
                max_slices=working_request.get("maxSlices") if isinstance(working_request.get("maxSlices"), int) else None,
                max_records=working_request.get("maxRecords") if isinstance(working_request.get("maxRecords"), int) else None,
                max_seconds=working_request.get("maxSeconds") if isinstance(working_request.get("maxSeconds"), int) else None,
            ),
        )

    @staticmethod
    def _has_explicit_filters(request: Mapping[str, object]) -> bool:
        return any(
            bool(request.get(field))
            for field in (
                "reasonCodes",
                "failureClass",
                "recordIdentifierType",
                "recordIdentifierValueContains",
                "search",
                "detectedAfter",
                "detectedBefore",
                "hashStripe",
                "hashStripeCount",
            )
        )

    @staticmethod
    def _request_signature(request: Mapping[str, object]) -> tuple[object, ...]:
        return (
            tuple(str(value).strip() for value in (request.get("reasonCodes") or []) if str(value).strip()),
            str(request.get("failureClass") or "").strip() or None,
            str(request.get("recordIdentifierType") or "").strip() or None,
            str(request.get("recordIdentifierValueContains") or "").strip() or None,
            str(request.get("search") or "").strip() or None,
            str(request.get("detectedAfter") or "").strip() or None,
            str(request.get("detectedBefore") or "").strip() or None,
            int(request.get("hashStripe")) if request.get("hashStripe") is not None else None,
            int(request.get("hashStripeCount")) if request.get("hashStripeCount") is not None else None,
            int(request.get("sliceLimit") or 0),
        )

    @staticmethod
    def _build_request_from_suggestion(request: Mapping[str, object], suggestion: Mapping[str, object]) -> dict[str, object]:
        next_request = dict(request)
        next_request["reasonCodes"] = [str(value).strip() for value in (suggestion.get("reasonCodes") or []) if str(value).strip()]
        next_request["failureClass"] = str(suggestion.get("failureClass") or "").strip() or None
        next_request["recordIdentifierType"] = str(suggestion.get("recordIdentifierType") or "").strip() or None
        next_request["recordIdentifierValueContains"] = str(suggestion.get("recordIdentifierValueContains") or "").strip() or None
        next_request["search"] = str(suggestion.get("search") or "").strip() or None
        next_request["detectedAfter"] = str(suggestion.get("detectedAfter") or "").strip() or None
        next_request["detectedBefore"] = str(suggestion.get("detectedBefore") or "").strip() or None
        next_request["hashStripe"] = int(suggestion.get("hashStripe")) if suggestion.get("hashStripe") is not None else None
        next_request["hashStripeCount"] = int(suggestion.get("hashStripeCount")) if suggestion.get("hashStripeCount") is not None else None
        next_request["sliceLimit"] = ExceptionAnalysisSessionService._choose_next_slice_limit(
            current_slice_limit=int(request.get("sliceLimit") or 1),
            remaining_count=int(suggestion.get("remainingCount") or 0),
        )
        return next_request

    async def _build_slice_response(self, row: Mapping[str, object], *, summary_only: bool) -> dict[str, object]:
        if summary_only:
            return {**self._build_slice_summary(row), "records": []}
        return await self._build_slice_detail(row)

    @staticmethod
    def _seed_request_from_session(last_slice: Mapping[str, object], request: Mapping[str, object]) -> dict[str, object]:
        suggestion = last_slice.get("nextSliceSuggestion") if isinstance(last_slice.get("nextSliceSuggestion"), Mapping) else None
        if suggestion is None:
            return dict(request)
        return ExceptionAnalysisSessionService._build_request_from_suggestion(request, suggestion)

    @staticmethod
    def _choose_next_slice_limit(*, current_slice_limit: int, remaining_count: int) -> int:
        current_slice_limit = max(int(current_slice_limit), 1)
        remaining_count = max(int(remaining_count), 0)
        if remaining_count == 0:
            return current_slice_limit
        if remaining_count <= current_slice_limit:
            return remaining_count
        if remaining_count > current_slice_limit * 10:
            return min(200, current_slice_limit * 2)
        return current_slice_limit

    @staticmethod
    def _build_analysis_status(
        *,
        slices: Sequence[Mapping[str, object]],
        current_slice: Mapping[str, object],
        state: str | None = None,
        reason: str | None = None,
        exhausted: bool = False,
        budget_hit: bool = False,
        stalled: bool = False,
        max_slices: int | None = None,
        max_records: int | None = None,
        max_seconds: int | None = None,
    ) -> dict[str, object]:
        current_suggestion = current_slice.get("nextSliceSuggestion") if isinstance(current_slice, Mapping) else None
        remaining_count = int(current_suggestion.get("remainingCount") or 0) if isinstance(current_suggestion, Mapping) else 0
        materialized_record_count = sum(int(row.get("returnedCount") or 0) for row in slices if isinstance(row, Mapping))
        anchor_total_count = int(current_slice.get("anchorTotalCount") or 0) if isinstance(current_slice, Mapping) else 0
        progress_percent = round((materialized_record_count / anchor_total_count) * 100.0, 1) if anchor_total_count > 0 else 0.0
        estimated_remaining_slice_count = ExceptionAnalysisSessionService._estimate_remaining_slice_count(current_slice=current_slice, remaining_count=remaining_count)
        estimated_cost_impact = (
            "No additional analysis cost is expected."
            if remaining_count <= 0
            else f"Approximately {estimated_remaining_slice_count} additional slice(s) covering {remaining_count} uncovered record(s)."
        )
        if state is None:
            if exhausted:
                state = "complete"
            elif budget_hit:
                state = "budget_hit"
            elif stalled:
                state = "stalled"
            elif remaining_count > 0:
                state = "in_progress"
            else:
                state = "complete"
        return {
            "state": state,
            "reason": reason or (
                "The analysis session has remaining uncovered exception space."
                if remaining_count > 0
                else "The analysis session exhausted the uncovered exception space."
            ),
            "progressPercent": progress_percent,
            "remainingCount": remaining_count,
            "estimatedRemainingRecordCount": remaining_count,
            "estimatedRemainingSliceCount": estimated_remaining_slice_count,
            "estimatedCostImpact": estimated_cost_impact,
            "sliceCount": len(list(slices)),
            "materializedRecordCount": materialized_record_count,
            "maxSlices": max_slices,
            "maxRecords": max_records,
            "maxSeconds": max_seconds,
            "budgetHit": budget_hit,
            "exhausted": exhausted,
            "stalled": stalled,
        }

    @staticmethod
    def _estimate_remaining_slice_count(*, current_slice: Mapping[str, object], remaining_count: int) -> int:
        if remaining_count <= 0:
            return 0
        slice_limit = max(int(current_slice.get("sliceLimit") or 1) if isinstance(current_slice, Mapping) else 1, 1)
        return max(1, math.ceil(remaining_count / slice_limit))

    async def _build_slice_detail(self, row: Mapping[str, object]) -> dict[str, object]:
        payload = await self._storage_backend.load_analysis_pack(str(row.get("analysisPackUri") or ""))
        records = payload.get("records") if isinstance(payload.get("records"), list) else []
        suggestion = payload.get("nextSliceSuggestion") if isinstance(payload.get("nextSliceSuggestion"), Mapping) else None
        return {
            **self._build_slice_summary(row),
            "records": [dict(record) for record in records if isinstance(record, Mapping)],
            "nextSliceSuggestion": dict(suggestion) if suggestion is not None else None,
        }

    def _build_slice_summary(self, row: Mapping[str, object]) -> dict[str, object]:
        return {
            "analysisSessionId": str(row.get("analysisSessionId") or ""),
            "analysisSliceId": str(row.get("analysisSliceId") or ""),
            "sliceIndex": int(row.get("sliceIndex") or 0),
            "dataObjectVersionId": str(row.get("dataObjectVersionId") or ""),
            "executionRunId": str(row.get("executionRunId") or ""),
            "ruleId": str(row.get("ruleId") or ""),
            "sliceLimit": int(row.get("sliceLimit") or 0),
            "anchorTotalCount": int(row.get("anchorTotalCount") or 0),
            "totalMatchingCount": int(row.get("totalMatchingCount") or 0),
            "returnedCount": int(row.get("returnedCount") or 0),
            "truncated": bool(row.get("truncated") or False),
            "analysisPackUri": str(row.get("analysisPackUri") or ""),
            "analysisPackSha256": str(row.get("analysisPackSha256") or ""),
            "analysisManifestUri": str(row.get("analysisManifestUri") or ""),
            "analysisManifestSha256": str(row.get("analysisManifestSha256") or ""),
            "filters": dict(row.get("filters") or {}),
            "nextSliceSuggestion": dict(row.get("nextSliceSuggestion")) if isinstance(row.get("nextSliceSuggestion"), Mapping) else None,
            "createdAt": str(row.get("createdAt") or ""),
            "updatedAt": str(row.get("updatedAt") or ""),
        }

    async def _build_session_payload(
        self,
        *,
        slices: Sequence[Mapping[str, object]],
        current_slice: Mapping[str, object],
        analysis_status: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        first = slices[0]
        return {
            "analysisSessionId": str(first.get("analysisSessionId") or ""),
            "dataObjectVersionId": str(first.get("dataObjectVersionId") or ""),
            "executionRunId": str(first.get("executionRunId") or ""),
            "ruleId": str(first.get("ruleId") or ""),
            "anchorTotalCount": int(first.get("anchorTotalCount") or 0),
            "sliceCount": len(list(slices)),
            "createdAt": str(first.get("createdAt") or ""),
            "updatedAt": str(current_slice.get("updatedAt") or ""),
            "analysisStatus": dict(analysis_status) if analysis_status is not None else self._build_analysis_status(slices=slices, current_slice=current_slice),
            "currentSlice": dict(current_slice),
            "slices": [self._build_slice_summary(row) for row in slices],
        }

    @staticmethod
    def _normalize_request(request: Mapping[str, object]) -> dict[str, object]:
        normalized_reason_codes = [str(value).strip() for value in (request.get("reasonCodes") or []) if str(value).strip()]
        slice_limit = int(request.get("sliceLimit") or 200)
        if slice_limit < 1:
            raise ValueError("slice_limit must be positive")
        normalized_detected_after = str(request.get("detectedAfter") or "").strip() or None
        normalized_detected_before = str(request.get("detectedBefore") or "").strip() or None
        hash_stripe = int(request.get("hashStripe")) if request.get("hashStripe") not in (None, "") else None
        hash_stripe_count = int(request.get("hashStripeCount")) if request.get("hashStripeCount") not in (None, "") else None
        if (hash_stripe is None) != (hash_stripe_count is None):
            raise ValueError("hash stripe requests require both hashStripe and hashStripeCount")
        if hash_stripe is not None and hash_stripe_count is not None:
            if hash_stripe_count < 1:
                raise ValueError("hashStripeCount must be positive")
            if hash_stripe < 0 or hash_stripe >= hash_stripe_count:
                raise ValueError("hashStripe must be within the stripe count")
        if normalized_detected_after is not None and normalized_detected_before is not None:
            detected_after_dt = datetime.fromisoformat(normalized_detected_after.replace("Z", "+00:00"))
            detected_before_dt = datetime.fromisoformat(normalized_detected_before.replace("Z", "+00:00"))
            if detected_after_dt > detected_before_dt:
                raise ValueError("detectedAfter must be before detectedBefore")
        return {
            "dataObjectVersionId": str(request.get("dataObjectVersionId") or "").strip(),
            "executionRunId": str(request.get("executionRunId") or "").strip(),
            "ruleId": str(request.get("ruleId") or "").strip(),
            "reasonCodes": normalized_reason_codes,
            "failureClass": str(request.get("failureClass") or "").strip() or None,
            "recordIdentifierType": str(request.get("recordIdentifierType") or "").strip() or None,
            "recordIdentifierValueContains": str(request.get("recordIdentifierValueContains") or "").strip() or None,
            "search": str(request.get("search") or "").strip() or None,
            "detectedAfter": normalized_detected_after,
            "detectedBefore": normalized_detected_before,
            "hashStripe": hash_stripe,
            "hashStripeCount": hash_stripe_count,
            "sliceLimit": min(slice_limit, 200),
            "runUntilExhausted": bool(request.get("runUntilExhausted") or False),
            "maxSlices": int(request.get("maxSlices")) if request.get("maxSlices") not in (None, "") else None,
            "maxRecords": int(request.get("maxRecords")) if request.get("maxRecords") not in (None, "") else None,
            "maxSeconds": int(request.get("maxSeconds")) if request.get("maxSeconds") not in (None, "") else None,
            "summaryOnly": bool(request.get("summaryOnly") or False),
        }

    @staticmethod
    def _build_next_slice_suggestion(request: Mapping[str, object], uncovered_records: Sequence[Mapping[str, object]]) -> dict[str, object] | None:
        normalized_reason_codes = {str(value).strip() for value in (request.get("reasonCodes") or []) if str(value).strip()}
        current_failure_class = str(request.get("failureClass") or "").strip() or None
        current_identifier_type = str(request.get("recordIdentifierType") or "").strip() or None
        current_detected_after = str(request.get("detectedAfter") or "").strip() or None
        current_detected_before = str(request.get("detectedBefore") or "").strip() or None
        current_hash_stripe = int(request.get("hashStripe")) if request.get("hashStripe") is not None else None
        current_hash_stripe_count = int(request.get("hashStripeCount")) if request.get("hashStripeCount") is not None else None
        stripe_count = 8

        uncovered_reason_counts: Counter[str] = Counter()
        uncovered_failure_class_counts: Counter[str] = Counter()
        uncovered_identifier_type_counts: Counter[str] = Counter()
        uncovered_day_counts: Counter[str] = Counter()
        uncovered_hash_stripe_counts: Counter[int] = Counter()

        for record in uncovered_records:
            ops_metadata = dict(record.get("opsMetadata") or {})
            reason_code = str(ops_metadata.get("reason_code") or "").strip()
            if reason_code:
                uncovered_reason_counts[reason_code] += 1
            failure_class = str(ops_metadata.get("failure_class") or "").strip()
            if failure_class:
                uncovered_failure_class_counts[failure_class] += 1
            identifier_type = str(ops_metadata.get("record_identifier_type") or "").strip()
            if identifier_type:
                uncovered_identifier_type_counts[identifier_type] += 1
            detected_at = ExceptionAnalysisSessionService._parse_detected_at(record.get("detectedAt"))
            if detected_at is not None:
                uncovered_day_counts[detected_at.date().isoformat()] += 1
            uncovered_hash_stripe_counts[ExceptionAnalysisSessionService._hash_stripe_for_record(record, stripe_count)] += 1

        if not uncovered_records:
            return {
                "reasonCodes": [],
                "failureClass": None,
                "recordIdentifierType": None,
                "recordIdentifierValueContains": None,
                "search": None,
                "detectedAfter": None,
                "detectedBefore": None,
                "hashStripe": None,
                "hashStripeCount": None,
                "remainingCount": 0,
                "partitionStrategy": [],
                "rationale": "The current slice already covers the entire analysis set.",
            }

        for reason_code, total in uncovered_reason_counts.most_common():
            if reason_code not in normalized_reason_codes:
                return {
                    "reasonCodes": [reason_code],
                    "failureClass": None,
                    "recordIdentifierType": None,
                    "recordIdentifierValueContains": None,
                    "search": None,
                    "detectedAfter": None,
                    "detectedBefore": None,
                    "hashStripe": None,
                    "hashStripeCount": None,
                    "remainingCount": len(uncovered_records),
                    "partitionStrategy": ["reason_code"],
                    "rationale": f"{total} uncovered exception facts share reason_code '{reason_code}'.",
                }

        if uncovered_failure_class_counts:
            failure_class, total = uncovered_failure_class_counts.most_common(1)[0]
            if failure_class != current_failure_class:
                return {
                    "reasonCodes": sorted(normalized_reason_codes),
                    "failureClass": failure_class,
                    "recordIdentifierType": None,
                    "recordIdentifierValueContains": None,
                    "search": None,
                    "detectedAfter": None,
                    "detectedBefore": None,
                    "hashStripe": None,
                    "hashStripeCount": None,
                    "remainingCount": len(uncovered_records),
                    "partitionStrategy": ["reason_code", "failure_class"],
                    "rationale": f"{total} uncovered exception facts share failure_class '{failure_class}'.",
                }

        if uncovered_identifier_type_counts:
            identifier_type, total = uncovered_identifier_type_counts.most_common(1)[0]
            if identifier_type != current_identifier_type:
                return {
                    "reasonCodes": sorted(normalized_reason_codes),
                    "failureClass": None,
                    "recordIdentifierType": identifier_type,
                    "recordIdentifierValueContains": None,
                    "search": None,
                    "detectedAfter": None,
                    "detectedBefore": None,
                    "hashStripe": None,
                    "hashStripeCount": None,
                    "remainingCount": len(uncovered_records),
                    "partitionStrategy": ["reason_code", "failure_class", "record_identifier_type"],
                    "rationale": f"{total} uncovered exception facts share record_identifier_type '{identifier_type}'.",
                }

        if len(uncovered_day_counts) > 1:
            day_value, total = uncovered_day_counts.most_common(1)[0]
            day_start = f"{day_value}T00:00:00+00:00"
            next_day = (datetime.fromisoformat(day_start.replace("Z", "+00:00")).astimezone(UTC) + timedelta(days=1)).isoformat()
            if day_start != current_detected_after or next_day != current_detected_before:
                return {
                    "reasonCodes": sorted(normalized_reason_codes),
                    "failureClass": None,
                    "recordIdentifierType": None,
                    "recordIdentifierValueContains": None,
                    "search": None,
                    "detectedAfter": day_start,
                    "detectedBefore": next_day,
                    "hashStripe": None,
                    "hashStripeCount": None,
                    "remainingCount": len(uncovered_records),
                    "partitionStrategy": ["detected_at_bucket"],
                    "rationale": f"{total} uncovered exception facts fall into detected_at day bucket '{day_value}'.",
                }

        if uncovered_hash_stripe_counts:
            hash_stripe, total = uncovered_hash_stripe_counts.most_common(1)[0]
            if current_hash_stripe is None or current_hash_stripe != hash_stripe or current_hash_stripe_count != stripe_count:
                return {
                    "reasonCodes": sorted(normalized_reason_codes),
                    "failureClass": None,
                    "recordIdentifierType": None,
                    "recordIdentifierValueContains": None,
                    "search": None,
                    "detectedAfter": None,
                    "detectedBefore": None,
                    "hashStripe": hash_stripe,
                    "hashStripeCount": stripe_count,
                    "remainingCount": len(uncovered_records),
                    "partitionStrategy": ["hash_stripe"],
                    "rationale": f"{total} uncovered exception facts fall into hash stripe {hash_stripe} of {stripe_count}.",
                }

        return {
            "reasonCodes": sorted(normalized_reason_codes),
            "failureClass": None,
            "recordIdentifierType": None,
            "recordIdentifierValueContains": None,
            "search": None,
            "detectedAfter": None,
            "detectedBefore": None,
            "hashStripe": None,
            "hashStripeCount": None,
            "remainingCount": len(uncovered_records),
            "partitionStrategy": ["reason_code", "failure_class", "record_identifier_type", "search"],
            "rationale": "Run the next slice with a narrower search term to inspect the remaining exception space.",
        }

    @staticmethod
    def _parse_detected_at(value: object) -> datetime | None:
        payload = str(value or "").strip()
        if not payload:
            return None
        parsed = datetime.fromisoformat(payload.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _hash_stripe_for_record(record: Mapping[str, object], stripe_count: int) -> int:
        identifier = str(record.get("dataPrimaryKey") or record.get("id") or "").strip()
        if not identifier:
            return 0
        digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
        return int(digest[:16], 16) % max(int(stripe_count), 1)

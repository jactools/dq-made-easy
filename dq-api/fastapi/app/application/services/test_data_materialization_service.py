from __future__ import annotations

import os
import re
from collections.abc import Awaitable, Callable, Mapping
from hashlib import sha256
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from app.core.runtime_queues import resolve_test_data_materialization_queue_key as _resolve_runtime_materialization_queue_key
from app.core.otel_metrics import record_async_queue_event


_REAL_EVIDENCE_OUTPUT_URI_TERMS = (
	"evidence",
	"reporting",
	"regulatory",
	"compliance",
	"production",
	"operational",
)


def resolve_test_data_redis_url(settings: Any) -> str | None:
	explicit_url = os.environ.get("PROFILING_REDIS_URL") or os.environ.get("REDIS_URL")
	if explicit_url:
		return explicit_url

	redis_host = str(getattr(settings, "redis_host", "") or "").strip()
	if not redis_host:
		return None

	redis_port = int(getattr(settings, "redis_port", 0) or 0)
	redis_db = int(getattr(settings, "redis_db", 0) or 0)
	redis_password = getattr(settings, "redis_password", None)
	if redis_password:
		from urllib.parse import quote

		return f"redis://:{quote(redis_password, safe='')}@{redis_host}:{redis_port}/{redis_db}"
	return f"redis://{redis_host}:{redis_port}/{redis_db}"


def resolve_test_data_materialization_queue_key() -> str:
	queue_key = _resolve_runtime_materialization_queue_key()
	if queue_key:
		return queue_key
	raise HTTPException(
		status_code=503,
		detail={
			"error": "test_data_materialization_queue_not_configured",
			"message": "Test data materialization queue is not configured",
			"env_vars": [
				"TEST_DATA_MATERIALIZATION_QUEUE_KEY",
				"DQ_TEST_DATA_MATERIALIZATION_QUEUE_KEY",
			],
		},
	)


def resolve_test_data_materialization_processing_queue_key(queue_key: str) -> str:
	return os.environ.get("TEST_DATA_MATERIALIZATION_PROCESSING_QUEUE_KEY") or f"{queue_key}:processing"


def resolve_test_data_output_prefix() -> str:
	prefix = str(os.environ.get("DQ_TEST_DATA_OUTPUT_PREFIX") or "").strip().rstrip("/")
	if not prefix:
		raise HTTPException(
			status_code=503,
			detail={
				"error": "test_data_output_not_configured",
				"message": "DQ_TEST_DATA_OUTPUT_PREFIX is not configured (expected e.g. s3a://dq-test-data)",
			},
		)
	return prefix


def default_materialization_output_uri(
	*,
	output_prefix: str,
	version_id: str,
	output_format: str,
	sample_count: int,
	attribute_hash: str,
) -> str:
	prefix = str(output_prefix or "").strip().rstrip("/")
	fmt = str(output_format or "").strip().lower() or "parquet"
	normalized_hash = str(attribute_hash or "").strip() or "all"
	return (
		f"{prefix}/data_object_version_id={version_id}"
		f"/attr_hash={normalized_hash}"
		f"/sample_count={int(sample_count)}"
		f"/format={fmt}"
	)


def normalize_s3_uri(uri: str) -> str:
	raw = str(uri or "").strip()
	if raw.startswith("s3://"):
		return "s3a://" + raw[len("s3://") :]
	return raw


def parse_s3a_uri(uri: str) -> tuple[str, str]:
	normalized = normalize_s3_uri(uri)
	if not normalized.startswith("s3a://"):
		raise HTTPException(
			status_code=422,
			detail={
				"error": "invalid_output_uri",
				"message": "output_uri must use s3:// or s3a://",
				"output_uri": uri,
			},
		)
	remainder = normalized[len("s3a://") :]
	if not remainder:
		raise HTTPException(
			status_code=422,
			detail={
				"error": "invalid_output_uri",
				"message": "output_uri must include a bucket name",
				"output_uri": uri,
			},
		)
	if "/" not in remainder:
		return remainder, ""
	bucket, key = remainder.split("/", 1)
	return bucket, key


def matched_real_evidence_output_uri_terms(output_uri: str) -> list[str]:
	normalized = normalize_s3_uri(output_uri).lower()
	tokens = {token for token in re.split(r"[^a-z0-9]+", normalized) if token}
	return [term for term in _REAL_EVIDENCE_OUTPUT_URI_TERMS if term in tokens]


def ensure_synthetic_test_output_uri(
	*,
	output_uri: str,
	status_code: int,
	request_id: str | None = None,
	data_object_version_id: str | None = None,
	correlation_id: str | None = None,
) -> None:
	normalized_output_uri = normalize_s3_uri(output_uri)
	matched_terms = matched_real_evidence_output_uri_terms(normalized_output_uri)
	if not matched_terms:
		return

	detail: dict[str, Any] = {
		"error": "synthetic_output_namespace_conflict",
		"message": "Test-data materialization outputs cannot use real/evidence storage semantics without explicit handling",
		"output_uri": normalized_output_uri,
		"matched_terms": matched_terms,
		"expected_object_storage_classification": "synthetic_test",
		"expected_evidence_classification": "synthetic_result",
	}
	if str(request_id or "").strip():
		detail["request_id"] = str(request_id).strip()
	if str(data_object_version_id or "").strip():
		detail["data_object_version_id"] = str(data_object_version_id).strip()
	if str(correlation_id or "").strip():
		detail["correlation_id"] = str(correlation_id).strip()
	raise HTTPException(status_code=status_code, detail=detail)


def resolve_optional_bool_env(name: str) -> bool | None:
	raw = os.getenv(name)
	if raw is None or not str(raw).strip():
		return None
	return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def derive_s3_ssl_enabled() -> bool:
	explicit = resolve_optional_bool_env("DQ_S3_SSL_ENABLED")
	if explicit is not None:
		return bool(explicit)
	endpoint = str(os.getenv("DQ_S3_ENDPOINT") or os.getenv("AWS_ENDPOINT_URL") or "").strip().lower()
	return endpoint.startswith("https://")


def build_s3_client() -> Any:
	try:
		import boto3
	except Exception as exc:  # pragma: no cover
		raise HTTPException(
			status_code=503,
			detail={
				"error": "dependency_missing",
				"message": "Python package 'boto3' is required for test data reuse checks",
				"dependency": "boto3",
			},
		) from exc

	endpoint = str(os.getenv("DQ_S3_ENDPOINT") or os.getenv("AWS_ENDPOINT_URL") or "").strip()
	access_key = str(os.getenv("DQ_S3_ACCESS_KEY") or os.getenv("AWS_ACCESS_KEY_ID") or "").strip()
	secret_key = str(os.getenv("DQ_S3_SECRET_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY") or "").strip()
	region = str(os.getenv("DQ_S3_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "").strip() or "us-east-1"

	if not endpoint:
		raise HTTPException(
			status_code=503,
			detail={
				"error": "s3_not_configured",
				"message": "DQ_S3_ENDPOINT/AWS_ENDPOINT_URL is required for test data reuse checks",
			},
		)
	if not (access_key and secret_key):
		raise HTTPException(
			status_code=503,
			detail={
				"error": "s3_not_configured",
				"message": "DQ_S3_ACCESS_KEY/DQ_S3_SECRET_KEY (or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY) is required for test data reuse checks",
			},
		)

	return boto3.client(
		"s3",
		endpoint_url=endpoint,
		aws_access_key_id=access_key,
		aws_secret_access_key=secret_key,
		region_name=region,
		verify=derive_s3_ssl_enabled(),
	)


def s3_prefix_has_objects(*, output_uri: str, build_s3_client_fn: Callable[[], Any] | None = None) -> bool:
	bucket, key_prefix = parse_s3a_uri(output_uri)
	normalized_prefix = str(key_prefix or "").lstrip("/")
	if normalized_prefix and not normalized_prefix.endswith("/"):
		normalized_prefix = f"{normalized_prefix}/"
	client = (build_s3_client_fn or build_s3_client)()
	try:
		response = client.list_objects_v2(Bucket=bucket, Prefix=normalized_prefix, MaxKeys=1)
	except HTTPException:
		raise
	except Exception as exc:
		raise HTTPException(
			status_code=503,
			detail={
				"error": "test_data_output_check_failed",
				"message": "Unable to check existing test data output in S3-compatible storage",
				"output_uri": output_uri,
			},
		) from exc
	return bool(response.get("Contents"))


def build_attribute_payloads(attributes: list[Any]) -> list[dict[str, Any]]:
	payloads: list[dict[str, Any]] = []
	for attribute in attributes:
		if hasattr(attribute, "model_dump"):
			payload = attribute.model_dump(
				mode="python",
				by_alias=attribute.__class__.__name__ == "TestDataAttributeRequest",
			)
		elif hasattr(attribute, "__dict__"):
			payload = vars(attribute)
		else:
			payload = dict(attribute)
		payloads.append(
			{
				"name": str(payload.get("name") or "").strip(),
				"type": str(payload.get("type") or "text").strip() or "text",
				"nullable": bool(payload.get("nullable", True)),
				"format": str(payload.get("format") or "").strip(),
				"is_primary_key": bool(payload.get("is_primary_key", payload.get("isPrimaryKey", False))),
			}
		)
	return [payload for payload in payloads if payload["name"]]


def test_data_materialization_request_key(request_id: str) -> str:
	return f"test-data-materialization-request:{request_id}"


async def write_test_data_materialization_record(
	redis_url: str,
	record: Any,
	ttl_seconds: int,
	request_key_builder: Callable[[str], str],
	record_payload_builder: Callable[[Any], dict[str, Any]],
	redis_set_json,
) -> None:
	record_payload = record_payload_builder(record)
	await redis_set_json(
		redis_url,
		request_key_builder(str(record_payload["request_id"])),
		record_payload,
		ttl_seconds,
	)


async def read_test_data_materialization_record(
	redis_url: str,
	request_id: str,
	request_key_builder: Callable[[str], str],
	require_record: Callable[[Any], Any],
	redis_get_json,
) -> Any | None:
	payload = await redis_get_json(redis_url, request_key_builder(request_id))
	if payload is None:
		return None
	return require_record(payload)


async def register_materialized_delivery_completion(
	*,
	request_id: str,
	payload: Any,
	catalog_repository: Any,
	resolve_redis_url: Callable[[], str | None],
	read_record: Callable[[str, str], Awaitable[Any | None]],
	require_record: Callable[[Any], Any],
	normalize_s3_uri_fn: Callable[[str], str],
	ensure_synthetic_output_uri_fn: Callable[..., None],
	create_completions_from_record: Callable[..., Any],
	build_completion_response: Callable[[Any], Any],
) -> Any:
	redis_url = resolve_redis_url()
	if not redis_url:
		raise HTTPException(status_code=503, detail="Test data materialization queue is not configured")
	record = await read_record(redis_url, request_id)
	if record is None:
		raise HTTPException(status_code=404, detail=f"Test data materialization '{request_id}' not found")
	record_entity = require_record(record)
	expected_output_uri = normalize_s3_uri_fn(str(getattr(record_entity, "output_uri", "") or "").strip())
	reported_output_uri = normalize_s3_uri_fn(str(getattr(payload, "output_uri", "") or "").strip())
	if expected_output_uri and reported_output_uri and expected_output_uri != reported_output_uri:
		raise HTTPException(
			status_code=409,
			detail={
				"error": "materialization_output_mismatch",
				"message": "Reported output_uri does not match the materialization request record",
				"request_id": request_id,
				"expected_output_uri": expected_output_uri,
				"reported_output_uri": reported_output_uri,
			},
		)
	expected_output_format = str(getattr(record_entity, "output_format", "") or "").strip().lower()
	reported_output_format = str(getattr(payload, "output_format", "") or "").strip().lower()
	if expected_output_format and reported_output_format and expected_output_format != reported_output_format:
		raise HTTPException(
			status_code=409,
			detail={
				"error": "materialization_format_mismatch",
				"message": "Reported output_format does not match the materialization request record",
				"request_id": request_id,
				"expected_output_format": expected_output_format,
				"reported_output_format": reported_output_format,
			},
		)
	ensure_synthetic_output_uri_fn(
		output_uri=reported_output_uri or expected_output_uri,
		status_code=409,
		request_id=request_id,
		data_object_version_id=str(getattr(record_entity, "data_object_version_id", "") or "").strip() or None,
		correlation_id=str(getattr(record_entity, "correlation_id", "") or "").strip() or None,
	)
	batch = create_completions_from_record(
		request_id=request_id,
		record=record_entity,
		target_results=[
			{
				"data_object_version_id": str(getattr(record_entity, "data_object_version_id", "") or "").strip(),
				"row_count": int(getattr(payload, "row_count", 0) or 0),
				"output_uri": reported_output_uri or expected_output_uri,
				"output_format": reported_output_format or expected_output_format,
			}
		],
		catalog_repository=catalog_repository,
		reused_existing=False,
	)
	return build_completion_response(batch.data_deliveries[0])


async def register_materialized_delivery_completions(
	*,
	request_id: str,
	target_results: list[Any],
	catalog_repository: Any,
	resolve_redis_url: Callable[[], str | None],
	read_record: Callable[[str, str], Awaitable[Any | None]],
	require_record: Callable[[Any], Any],
	expected_targets_from_record: Callable[[Any], list[dict[str, Any]]],
	normalize_s3_uri_fn: Callable[[str], str],
	ensure_synthetic_output_uri_fn: Callable[..., None],
	create_completions_from_record: Callable[..., Any],
) -> Any:
	redis_url = resolve_redis_url()
	if not redis_url:
		raise HTTPException(status_code=503, detail="Test data materialization queue is not configured")
	record = await read_record(redis_url, request_id)
	if record is None:
		raise HTTPException(status_code=404, detail=f"Test data materialization '{request_id}' not found")
	record_entity = require_record(record)
	expected_targets = expected_targets_from_record(record_entity)
	expected_by_version = {
		str(target.get("data_object_version_id") or "").strip(): target
		for target in expected_targets
		if str(target.get("data_object_version_id") or "").strip()
	}
	provided_versions = [str(getattr(target, "data_object_version_id", "") or "").strip() for target in target_results]
	if set(provided_versions) != set(expected_by_version.keys()) or len(provided_versions) != len(expected_by_version):
		raise HTTPException(
			status_code=409,
			detail={
				"error": "materialization_target_mismatch",
				"message": "Reported target results do not match the materialization request record",
				"request_id": request_id,
				"expected_data_object_version_ids": sorted(expected_by_version.keys()),
				"reported_data_object_version_ids": sorted(provided_versions),
			},
		)
	normalized_results: list[dict[str, Any]] = []
	for target in target_results:
		version_id = str(getattr(target, "data_object_version_id", "") or "").strip()
		expected = expected_by_version[version_id]
		expected_output_uri = normalize_s3_uri_fn(str(expected.get("output_uri") or "").strip())
		reported_output_uri = normalize_s3_uri_fn(str(getattr(target, "output_uri", "") or "").strip())
		if expected_output_uri and reported_output_uri and expected_output_uri != reported_output_uri:
			raise HTTPException(
				status_code=409,
				detail={
					"error": "materialization_output_mismatch",
					"message": "Reported output_uri does not match the materialization request record",
					"request_id": request_id,
					"data_object_version_id": version_id,
					"expected_output_uri": expected_output_uri,
					"reported_output_uri": reported_output_uri,
				},
			)
		expected_output_format = str(expected.get("output_format") or getattr(record_entity, "output_format", "") or "").strip().lower()
		reported_output_format = str(getattr(target, "output_format", "") or "").strip().lower()
		if expected_output_format and reported_output_format and expected_output_format != reported_output_format:
			raise HTTPException(
				status_code=409,
				detail={
					"error": "materialization_format_mismatch",
					"message": "Reported output_format does not match the materialization request record",
					"request_id": request_id,
					"data_object_version_id": version_id,
					"expected_output_format": expected_output_format,
					"reported_output_format": reported_output_format,
				},
			)
		ensure_synthetic_output_uri_fn(
			output_uri=reported_output_uri or expected_output_uri,
			status_code=409,
			request_id=request_id,
			data_object_version_id=version_id,
			correlation_id=str(getattr(record_entity, "correlation_id", "") or "").strip() or None,
		)
		normalized_results.append(
			{
				"data_object_version_id": version_id,
				"row_count": int(getattr(target, "row_count", 0) or 0),
				"output_uri": reported_output_uri or expected_output_uri,
				"output_format": reported_output_format or expected_output_format,
			}
		)
	return create_completions_from_record(
		request_id=request_id,
		record=record_entity,
		target_results=normalized_results,
		catalog_repository=catalog_repository,
		reused_existing=False,
	)


async def enqueue_test_data_materialization_request(
	*,
	request_headers: Mapping[str, str],
	version_id: str,
	sample_count: int,
	output_format: str,
	output_uri: str | None,
	selected_attribute_names: list[str] | None,
	refresh: bool,
	catalog_repository: Any,
	selection: dict[str, Any] | None,
	targets: list[dict[str, Any]] | None,
	request_contract: str | None,
	resolve_redis_url: Callable[[], str | None],
	resolve_queue_key: Callable[[], str],
	resolve_processing_queue_key: Callable[[str], str],
	redis_llen,
	s3_prefix_has_objects_fn: Callable[..., bool],
	build_attribute_payloads_fn: Callable[[list[Any]], list[dict[str, Any]]],
	resolve_output_prefix: Callable[[], str],
	default_output_uri: Callable[..., str],
	ensure_synthetic_output_uri_fn: Callable[..., None],
	normalize_s3_uri_fn: Callable[[str], str],
	build_record: Callable[..., Any],
	create_completions_from_record: Callable[..., Any],
	build_result_from_deliveries: Callable[..., dict[str, Any]],
	current_timestamp: Callable[[], str],
	write_record: Callable[[str, Any], Awaitable[None]],
	push_queue,
	inject_queue_trace_headers: Callable[[dict[str, Any]], None],
	queue_job_type: str,
) -> Any:
	redis_url = resolve_redis_url()
	if not redis_url:
		raise HTTPException(status_code=503, detail="Test data materialization queue is not configured")
	queue_key = resolve_queue_key()
	processing_queue_key = resolve_processing_queue_key(queue_key)
	max_pending = int(os.environ.get("TEST_DATA_MATERIALIZATION_MAX_PENDING") or 20)
	max_in_flight = int(os.environ.get("TEST_DATA_MATERIALIZATION_MAX_IN_FLIGHT") or 5)
	try:
		pending_len = await redis_llen(redis_url, queue_key)
		in_flight_len = await redis_llen(redis_url, processing_queue_key)
	except HTTPException:
		raise
	except Exception as exc:
		raise HTTPException(status_code=503, detail="Unable to query Redis queue status") from exc
	if pending_len >= max_pending or in_flight_len >= max_in_flight:
		raise HTTPException(
			status_code=429,
			detail={
				"error": "queue_limit_exceeded",
				"message": "Test data materialization queue is at capacity",
				"queue_key": queue_key,
				"pending": pending_len,
				"in_flight": in_flight_len,
				"max_pending": max_pending,
				"max_in_flight": max_in_flight,
			},
		)
	request_id = f"tdm-{uuid4().hex[:12]}"
	job_id = f"tdmj-{uuid4().hex[:12]}"
	correlation_id = request_headers.get("X-Correlation-ID") or f"corr-{uuid4().hex[:12]}"
	resolved_targets: list[dict[str, Any]] = []
	if targets:
		for target in targets:
			if not isinstance(target, dict):
				continue
			target_version_id = str(target.get("data_object_version_id") or "").strip()
			target_output_uri = str(target.get("output_uri") or "").strip()
			target_output_format = str(target.get("output_format") or output_format or "").strip().lower()
			target_attributes = list(target.get("attributes") or [])
			target_sample_count = int(target.get("sample_count") or sample_count)
			if not target_version_id or not target_output_uri or not target_output_format or not target_attributes:
				raise HTTPException(
					status_code=422,
					detail={
						"error": "invalid_materialization_target",
						"message": "Each materialization target must include data_object_version_id, output_uri, output_format, sample_count, and attributes",
					},
				)
			ensure_synthetic_output_uri_fn(
				output_uri=target_output_uri,
				status_code=422,
				request_id=request_id,
				data_object_version_id=target_version_id,
				correlation_id=correlation_id,
			)
			resolved_targets.append(
				{
					"data_object_version_id": target_version_id,
					"sample_count": target_sample_count,
					"output_format": target_output_format,
					"output_uri": normalize_s3_uri_fn(target_output_uri),
					"attributes": target_attributes,
				}
			)
	else:
		attributes = build_attribute_payloads_fn(catalog_repository.list_attributes_catalog(version_id))
		if not attributes:
			raise HTTPException(
				status_code=422,
				detail={
					"error": "missing_attributes",
					"message": "Data object version has no attributes to generate test data",
					"data_object_version_id": version_id,
				},
			)
		selected = [str(name or "").strip() for name in (selected_attribute_names or []) if str(name or "").strip()]
		attribute_hash = "all"
		if selected:
			selected_set = {name for name in selected}
			filtered = [item for item in attributes if str(item.get("name") or "").strip() in selected_set]
			missing = sorted(selected_set.difference({str(item.get("name") or "").strip() for item in filtered}))
			if missing:
				raise HTTPException(
					status_code=422,
					detail={
						"error": "unknown_attributes",
						"message": "One or more selected_attribute_names were not found on the data object version",
						"data_object_version_id": version_id,
						"missing_attribute_names": missing,
					},
				)
			attributes = filtered
			joined = ",".join(sorted(selected_set))
			attribute_hash = sha256(joined.encode("utf-8")).hexdigest()[:12]
		if not attributes:
			raise HTTPException(
				status_code=422,
				detail={
					"error": "missing_attributes",
					"message": "No attributes remain after applying selected_attribute_names",
					"data_object_version_id": version_id,
				},
			)
		resolved_output_uri = str(output_uri or "").strip()
		if not resolved_output_uri:
			resolved_output_uri = default_output_uri(
				output_prefix=resolve_output_prefix(),
				version_id=version_id,
				output_format=output_format,
				sample_count=sample_count,
				attribute_hash=attribute_hash,
			)
		ensure_synthetic_output_uri_fn(
			output_uri=resolved_output_uri,
			status_code=422,
			request_id=request_id,
			data_object_version_id=version_id,
			correlation_id=correlation_id,
		)
		resolved_targets.append(
			{
				"data_object_version_id": version_id,
				"sample_count": int(sample_count),
				"output_format": str(output_format).strip().lower(),
				"output_uri": normalize_s3_uri_fn(resolved_output_uri),
				"attributes": attributes,
			}
		)
	primary_target = resolved_targets[0]
	request_output_uri = normalize_s3_uri_fn(str(output_uri or primary_target.get("output_uri") or "").strip())
	target_ids = [str(target.get("data_object_version_id") or "").strip() for target in resolved_targets]
	if not bool(refresh) and all(s3_prefix_has_objects_fn(output_uri=str(target.get("output_uri") or "")) for target in resolved_targets):
		job_payload = {
			"data_object_version_id": str(primary_target.get("data_object_version_id") or "").strip(),
			"sample_count": int(sample_count),
			"output_format": str(output_format).strip().lower(),
			"output_uri": request_output_uri,
			"attributes": list(primary_target.get("attributes") or []),
			"targets": resolved_targets,
		}
		record = build_record(
			request_id=request_id,
			job_id="reused",
			correlation_id=correlation_id,
			request_payload=job_payload,
			queue_key=queue_key,
			processing_queue_key=processing_queue_key,
			selection=selection,
			request_contract=request_contract,
			target_data_object_version_ids=target_ids,
		)
		completion = create_completions_from_record(
			request_id=request_id,
			record=record,
			target_results=[
				{
					"data_object_version_id": str(target.get("data_object_version_id") or "").strip(),
					"row_count": 0,
					"output_uri": str(target.get("output_uri") or "").strip(),
					"output_format": str(target.get("output_format") or output_format or "").strip().lower(),
				}
				for target in resolved_targets
			],
			catalog_repository=catalog_repository,
			reused_existing=True,
		)
		now = current_timestamp()
		record.status = "completed"
		record.started_at = now
		record.completed_at = now
		record.result = build_result_from_deliveries(
			deliveries=completion.data_deliveries,
			request_output_uri=request_output_uri,
			output_format=str(output_format).strip().lower(),
			reused_existing=True,
		)
		await write_record(redis_url, record)
		record_async_queue_event(
			service="dq-api",
			queue_type="test_data_materialization",
			stage="reuse_existing",
			result="success",
		)
		return record
	job_payload = {
		"data_object_version_id": str(primary_target.get("data_object_version_id") or "").strip(),
		"sample_count": int(sample_count),
		"output_format": str(output_format).strip().lower(),
		"output_uri": request_output_uri,
		"attributes": list(primary_target.get("attributes") or []),
		"targets": resolved_targets,
	}
	queue_payload = {
		"type": queue_job_type,
		"job_id": job_id,
		"materialization_request_id": request_id,
		"correlation_id": correlation_id,
		"headers": {},
		"payload": job_payload,
	}
	inject_queue_trace_headers(queue_payload)
	record = build_record(
		request_id=request_id,
		job_id=job_id,
		correlation_id=correlation_id,
		request_payload=job_payload,
		queue_key=queue_key,
		processing_queue_key=processing_queue_key,
		selection=selection,
		request_contract=request_contract,
		target_data_object_version_ids=target_ids,
	)
	await write_record(redis_url, record)
	try:
		await push_queue(redis_url, queue_key, queue_payload)
	except Exception as exc:
		failed_record = record.model_copy(
			update={
				"status": "failed",
				"completed_at": current_timestamp(),
				"error_message": f"Failed to enqueue materialization job: {exc}",
			}
		)
		await write_record(redis_url, failed_record)
		record_async_queue_event(
			service="dq-api",
			queue_type="test_data_materialization",
			stage="enqueue",
			result="failure",
		)
		raise HTTPException(status_code=503, detail="Failed to enqueue materialization job") from exc
	record_async_queue_event(
		service="dq-api",
		queue_type="test_data_materialization",
		stage="enqueue",
		result="success",
	)
	return record

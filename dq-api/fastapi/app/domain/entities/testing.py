from __future__ import annotations

from typing import Any

from pydantic import Field

from app.domain.entities.base import EntityModel


class ExecutionTraceEntity(EntityModel):
    executionId: str = ""
    correlationId: str | None = None
    executedAt: str | None = None
    resultStatus: str = ""
    artifactKey: str | None = None
    ruleVersionId: str | None = None
    ruleVersionNumber: int | None = None
    compilerVersion: str | None = None
    compilerRevision: int | None = None
    schemaVersion: str | None = None


class TestProofEntity(EntityModel):
    id: str
    ruleId: str = ""
    testDate: str = ""
    coverage: float = 0.0
    status: str = ""
    recordsTestedCount: int = 0
    failuresFound: int = 0
    proofData: dict[str, Any] = Field(default_factory=dict)
    executionTrace: ExecutionTraceEntity | None = None
    metrics: dict[str, Any] | None = None
    diagnostics: list[dict[str, Any]] | None = None


class BatchTestRequestEntity(EntityModel):
    id: str
    ruleId: str
    requestedBy: str
    requestedAt: str
    testDataConfig: dict[str, Any] = Field(default_factory=dict)
    executionCorrelationId: str | None = None
    status: str = "pending"
    workspace: str = "default"
    completedAt: str | None = None
    proofId: str | None = None


class TestRowResultEntity(EntityModel):
    rowIndex: int
    data: dict[str, Any]
    passed: bool
    joinEvaluated: bool = False
    joinMatchedContexts: int = 0


class TestRunResultEntity(EntityModel):
    ruleId: str
    expression: str
    testDataSource: str
    totalTests: int
    passedCount: int
    failedCount: int
    successRate: float
    rulePassed: bool = False
    requiredSuccessRate: float | None = None
    timestamp: str
    results: list[TestRowResultEntity] = Field(default_factory=list)
    ruleDetails: dict[str, Any] = Field(default_factory=dict)
    executionContext: dict[str, Any] | None = None


class TestDataPayloadEntity(EntityModel):
    versionId: str
    versionName: Any = None
    dataObjectId: Any = None
    attributeCount: int = 0
    sampleCount: int = 0
    samples: list[dict[str, Any]] = Field(default_factory=list)
    attributes: list[dict[str, Any]] = Field(default_factory=list)
    generatedAt: str


class StoreTestProofResultEntity(EntityModel):
    proofId: str
    ruleId: str
    testDate: str
    coverage: float
    passed: bool
    recordsTestedCount: int
    failuresFound: int
    successRate: float
    proofData: dict[str, Any] = Field(default_factory=dict)
    executionTrace: ExecutionTraceEntity | None = None
    metrics: dict[str, Any] | None = None
    diagnostics: list[dict[str, Any]] | None = None


class BatchTestRunResultEntity(EntityModel):
    id: str
    status: str
    executionContext: dict[str, Any] | None = None


class QueuedTestDataResultEntity(EntityModel):
    version_id: str = ""
    version_name: Any = None
    data_object_id: Any = None
    attribute_count: int = 0
    sample_count: int = 0
    samples: list[dict[str, Any]] = Field(default_factory=list)
    attributes: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: str | None = None


class QueuedTestDataRequestRecordEntity(EntityModel):
    request_id: str
    job_id: str
    businessKey: str | None = None
    status: str
    target_type: str
    target_id: str
    sample_count: int
    requested_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    correlation_id: str | None = None
    result: dict[str, Any] | None = None


class TestDataMaterializationRecordEntity(EntityModel):
    request_id: str
    job_id: str
    request_contract: str | None = None
    status: str
    data_object_version_id: str
    target_data_object_version_ids: list[str] = Field(default_factory=list)
    sample_count: int
    output_format: str
    output_uri: str
    requested_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    correlation_id: str | None = None
    queue_key: str | None = None
    processing_queue_key: str | None = None
    selection: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


def build_queued_test_data_result_entity(payload: Any) -> QueuedTestDataResultEntity | None:
    if not isinstance(payload, dict):
        return None

    raw_samples = payload.get("samples") if isinstance(payload.get("samples"), list) else []
    raw_attributes = payload.get("attributes") if isinstance(payload.get("attributes"), list) else []
    return QueuedTestDataResultEntity(
        version_id=str(payload.get("version_id") or "").strip(),
        version_name=payload.get("version_name"),
        data_object_id=payload.get("data_object_id"),
        attribute_count=int(payload.get("attribute_count") or 0),
        sample_count=int(payload.get("sample_count") or 0),
        samples=[dict(item) for item in raw_samples if isinstance(item, dict)],
        attributes=[dict(item) for item in raw_attributes if isinstance(item, dict)],
        generated_at=str(payload.get("generated_at") or "").strip() or None,
    )


def build_queued_test_data_request_record_entity(payload: Any) -> QueuedTestDataRequestRecordEntity | None:
    if not isinstance(payload, dict):
        return None

    request_id = str(payload.get("request_id") or "").strip()
    job_id = str(payload.get("job_id") or "").strip()
    target_type = str(payload.get("target_type") or "").strip()
    target_id = str(payload.get("target_id") or "").strip()
    requested_at = str(payload.get("requested_at") or "").strip()
    if not request_id or not job_id or not target_type or not target_id or not requested_at:
        return None

    return QueuedTestDataRequestRecordEntity(
        request_id=request_id,
        job_id=job_id,
        businessKey=str(payload.get("business_key") or "").strip() or None,
        status=str(payload.get("status") or "pending").strip() or "pending",
        target_type=target_type,
        target_id=target_id,
        sample_count=int(payload.get("sample_count") or 0),
        requested_at=requested_at,
        started_at=str(payload.get("started_at") or "").strip() or None,
        completed_at=str(payload.get("completed_at") or "").strip() or None,
        error_message=str(payload.get("error_message") or "").strip() or None,
        correlation_id=str(payload.get("correlation_id") or "").strip() or None,
        result=(dict(payload.get("result") or {}) if isinstance(payload.get("result"), dict) else None),
    )


def build_test_data_materialization_record_entity(payload: Any) -> TestDataMaterializationRecordEntity | None:
    if not isinstance(payload, dict):
        return None

    request_id = str(payload.get("request_id") or "").strip()
    job_id = str(payload.get("job_id") or "").strip()
    version_id = str(payload.get("data_object_version_id") or "").strip()
    output_format = str(payload.get("output_format") or "").strip()
    output_uri = str(payload.get("output_uri") or "").strip()
    if not request_id or not job_id or not version_id or not output_format or not output_uri:
        return None

    target_ids_raw = payload.get("target_data_object_version_ids")
    target_ids = [
        str(item or "").strip()
        for item in (target_ids_raw if isinstance(target_ids_raw, list) else [])
        if str(item or "").strip()
    ]

    return TestDataMaterializationRecordEntity(
        request_id=request_id,
        job_id=job_id,
        request_contract=str(payload.get("request_contract") or "").strip() or None,
        status=str(payload.get("status") or "pending").strip() or "pending",
        data_object_version_id=version_id,
        target_data_object_version_ids=target_ids,
        sample_count=int(payload.get("sample_count") or 0),
        output_format=output_format,
        output_uri=output_uri,
        requested_at=str(payload.get("requested_at") or "").strip() or None,
        started_at=str(payload.get("started_at") or "").strip() or None,
        completed_at=str(payload.get("completed_at") or "").strip() or None,
        error_message=str(payload.get("error_message") or "").strip() or None,
        correlation_id=str(payload.get("correlation_id") or "").strip() or None,
        queue_key=str(payload.get("queue_key") or "").strip() or None,
        processing_queue_key=str(payload.get("processing_queue_key") or "").strip() or None,
        selection=(dict(payload.get("selection") or {}) if isinstance(payload.get("selection"), dict) else None),
        result=(dict(payload.get("result") or {}) if isinstance(payload.get("result"), dict) else None),
    )

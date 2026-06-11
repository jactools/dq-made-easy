from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from app.domain.entities import GxArtifactEnvelopeEntity


class GxExecutionSourceAdapterError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class GxExecutionSourceAdapter(Protocol):
    def supports_execution_shape(self, execution_shape: str) -> bool:
        ...

    def resolve_asset(
        self,
        *,
        spark_session: Any,
        suite: GxArtifactEnvelopeEntity,
        data_object_version_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        ...

    def load_dataframe(self, *, spark_session: Any, asset_ref: Mapping[str, Any]) -> Any:
        ...

    def materialize_primary_key(self, dataframe: Any, primary_key_config: Sequence[str]) -> Any:
        ...

    def emit_validation_target(self, dataframe: Any, gx_context: Mapping[str, Any]) -> Any:
        ...


class PysparkExecutionSourceAdapter:
    def __init__(
        self,
        *,
        source_loader: Any | None = None,
        materialized_source_loader: Any | None = None,
    ) -> None:
        self._source_loader = source_loader
        self._materialized_source_loader = materialized_source_loader

    def supports_execution_shape(self, execution_shape: str) -> bool:
        normalized_shape = str(execution_shape or "").strip().lower()
        if normalized_shape in {"single_object", "streaming", "micro_batch"}:
            return self._source_loader is not None
        if normalized_shape == "join_pair":
            return self._materialized_source_loader is not None
        return False

    def resolve_asset(
        self,
        *,
        spark_session: Any,
        suite: GxArtifactEnvelopeEntity,
        data_object_version_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        del spark_session

        execution_contract = suite.executionContract
        if execution_contract is None:
            raise GxExecutionSourceAdapterError(
                f"GX suite '{suite.suiteId}' is missing an executionContract"
            )

        execution_shape = str(execution_contract.executionShape or "").strip()
        if not execution_shape:
            raise GxExecutionSourceAdapterError(
                f"GX suite '{suite.suiteId}' is missing an execution shape"
            )

        if execution_shape in {"single_object", "streaming", "micro_batch"}:
            source_ref = str(data_object_version_id or "").strip()
        elif execution_shape == "join_pair":
            source_materialization = execution_contract.sourceMaterialization
            if source_materialization is None:
                raise GxExecutionSourceAdapterError(
                    f"GX suite '{suite.suiteId}' declares join_pair execution without sourceMaterialization"
                )
            source_ref = str(source_materialization.outputLocation or "").strip()
        else:
            raise GxExecutionSourceAdapterError(
                f"GX suite '{suite.suiteId}' declares unsupported execution shape '{execution_shape}'"
            )

        if not source_ref:
            raise GxExecutionSourceAdapterError(
                f"GX suite '{suite.suiteId}' does not resolve to a source reference"
            )

        return {
            "suite_id": str(suite.suiteId or "").strip(),
            "suite_version": int(suite.suiteVersion),
            "execution_shape": execution_shape,
            "data_object_version_id": str(data_object_version_id or "").strip(),
            "source_ref": source_ref,
            "correlation_id": str(correlation_id or "").strip(),
        }

    def load_dataframe(self, *, spark_session: Any, asset_ref: Mapping[str, Any]) -> Any:
        execution_shape = str(asset_ref.get("execution_shape") or "").strip()
        source_ref = str(asset_ref.get("source_ref") or "").strip()
        if not source_ref:
            raise GxExecutionSourceAdapterError("GX execution asset reference does not include a source_ref")

        if execution_shape in {"single_object", "streaming", "micro_batch"}:
            if self._source_loader is None:
                raise GxExecutionSourceAdapterError(
                    "No source_loader was configured for single_object/streaming/micro_batch execution",
                    status_code=503,
                )
            loaded = self._source_loader(spark_session, source_ref)
        elif execution_shape == "join_pair":
            if self._materialized_source_loader is None:
                raise GxExecutionSourceAdapterError(
                    "No materialized_source_loader was configured for join_pair execution",
                    status_code=503,
                )
            loaded = self._materialized_source_loader(spark_session, source_ref)
        else:
            raise GxExecutionSourceAdapterError(
                f"GX execution asset reference declares unsupported execution shape '{execution_shape}'"
            )

        return self._normalize_handle(loaded, asset_ref)

    def materialize_primary_key(self, dataframe: Any, primary_key_config: Sequence[str]) -> Any:
        if not isinstance(dataframe, Mapping):
            return dataframe

        handle = dict(dataframe)
        handle["primary_key_fields"] = [
            str(field or "").strip()
            for field in primary_key_config
            if str(field or "").strip()
        ]
        return handle

    def emit_validation_target(self, dataframe: Any, gx_context: Mapping[str, Any]) -> Any:
        if not isinstance(dataframe, Mapping):
            return dataframe

        handle = dict(dataframe)
        handle["gx_context"] = dict(gx_context)
        return handle

    def _normalize_handle(self, loaded: Any, asset_ref: Mapping[str, Any]) -> Any:
        if isinstance(loaded, Mapping):
            handle = dict(loaded)
        else:
            handle = {"value": loaded}

        source_ref = str(asset_ref.get("source_ref") or "").strip()
        if source_ref and not str(handle.get("source_ref") or "").strip():
            handle["source_ref"] = source_ref
        handle["asset_ref"] = dict(asset_ref)
        return handle
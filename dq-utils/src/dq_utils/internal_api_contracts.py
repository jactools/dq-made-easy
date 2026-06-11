from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def _format_json_path(segments: tuple[Any, ...]) -> str:
    path = "$"
    for segment in segments:
        if isinstance(segment, int):
            path += f"[{segment}]"
            continue
        text = str(segment)
        if text.isidentifier():
            path += f".{text}"
            continue
        path += f"[{json.dumps(text)}]"
    return path


@dataclass(frozen=True)
class ContractValidationIssue:
    json_path: str
    schema_path: str
    message: str
    validator: str

    def as_dict(self) -> dict[str, str]:
        return {
            "json_path": self.json_path,
            "schema_path": self.schema_path,
            "message": self.message,
            "validator": self.validator,
        }


@dataclass(frozen=True)
class OperationContract:
    version: str
    method: str
    path: str
    operation_id: str
    request_body_required: bool
    request_body_schema_ref: str | None
    request_content_types: tuple[str, ...]


class InternalApiContractLookupError(RuntimeError):
    pass


class InternalApiContractValidationError(RuntimeError):
    def __init__(self, operation: OperationContract, issues: list[ContractValidationIssue]) -> None:
        self.operation = operation
        self.issues = tuple(issues)
        super().__init__(
            f"Request payload does not match contract for {operation.method} {operation.path} ({operation.operation_id})"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation.operation_id,
            "path": self.operation.path,
            "method": self.operation.method,
            "validation_errors": [issue.as_dict() for issue in self.issues],
        }


class InternalApiContractRegistry:
    def __init__(self, contracts_root: str | Path) -> None:
        self._contracts_root = Path(contracts_root)
        self._operations: dict[tuple[str, str], OperationContract] = {}
        self._schema_bundles: dict[str, dict[str, Any]] = {}
        self._validators: dict[tuple[str, str], Draft202012Validator] = {}
        self._load()

    @property
    def contracts_root(self) -> Path:
        return self._contracts_root

    def get_operation(self, method: str, path: str) -> OperationContract | None:
        return self._operations.get((str(method or "").upper(), str(path or "")))

    def validate_request_payload(self, method: str, path: str, payload: Any) -> OperationContract:
        operation = self.get_operation(method, path)
        if operation is None:
            raise InternalApiContractLookupError(f"No internal API contract found for {method} {path}")
        if operation.request_body_schema_ref is None:
            return operation

        validator = self._get_validator(operation.version, operation.request_body_schema_ref)
        errors = sorted(validator.iter_errors(payload), key=lambda err: (list(err.path), list(err.schema_path)))
        if not errors:
            return operation

        issues = [
            ContractValidationIssue(
                json_path=_format_json_path(tuple(error.path)),
                schema_path=_format_json_path(tuple(error.schema_path)),
                message=error.message,
                validator=str(error.validator),
            )
            for error in errors
        ]
        raise InternalApiContractValidationError(operation, issues)

    def _get_validator(self, version: str, schema_ref: str) -> Draft202012Validator:
        cache_key = (version, schema_ref)
        cached = self._validators.get(cache_key)
        if cached is not None:
            return cached

        schema_bundle = self._schema_bundles.get(version)
        if schema_bundle is None:
            raise InternalApiContractLookupError(f"No schema bundle loaded for internal API version {version}")

        validation_schema = {
            "$schema": schema_bundle.get("$schema", "https://json-schema.org/draft/2020-12/schema"),
            "$defs": schema_bundle.get("$defs", {}),
            "allOf": [{"$ref": schema_ref}],
        }
        validator = Draft202012Validator(validation_schema)
        self._validators[cache_key] = validator
        return validator

    def _load(self) -> None:
        index_path = self._contracts_root / "index.json"
        if not index_path.exists():
            raise RuntimeError(f"Internal API contract index is missing: {index_path}")

        index_payload = json.loads(index_path.read_text())
        contracts = index_payload.get("contracts")
        if not isinstance(contracts, list):
            raise RuntimeError(f"Internal API contract index is invalid: {index_path}")

        aggregate_contracts = [
            contract for contract in contracts if isinstance(contract, dict) and contract.get("kind") == "aggregate"
        ]
        if not aggregate_contracts:
            raise RuntimeError(f"Internal API contract index has no aggregate bundle entries: {index_path}")

        for contract in aggregate_contracts:
            version = str(contract.get("version") or "").strip()
            files = contract.get("files") or {}
            schema_path = self._contracts_root / str(files.get("schema") or "")
            operations_path = self._contracts_root / str(files.get("operations") or "")
            if not version or not schema_path.exists() or not operations_path.exists():
                raise RuntimeError(
                    f"Internal API aggregate contract bundle is incomplete for version {version or '<unknown>'}: {contract}"
                )

            schema_bundle = json.loads(schema_path.read_text())
            operations_manifest = json.loads(operations_path.read_text())
            operations = operations_manifest.get("operations")
            if not isinstance(operations, list):
                raise RuntimeError(f"Internal API operations manifest is invalid: {operations_path}")

            self._schema_bundles[version] = schema_bundle
            for operation in operations:
                if not isinstance(operation, dict):
                    continue
                method = str(operation.get("method") or "").upper()
                path = str(operation.get("path") or "")
                operation_id = str(operation.get("operation_id") or "").strip()
                request_body = operation.get("request_body") or {}
                content = request_body.get("content") or {}
                request_content_types = tuple(sorted(str(media_type) for media_type in content.keys()))
                application_json = content.get("application/json") if isinstance(content, dict) else None
                schema_ref = None
                if isinstance(application_json, dict):
                    schema_ref = application_json.get("schema_ref")

                self._operations[(method, path)] = OperationContract(
                    version=version,
                    method=method,
                    path=path,
                    operation_id=operation_id,
                    request_body_required=bool(request_body.get("required", False)),
                    request_body_schema_ref=str(schema_ref) if schema_ref else None,
                    request_content_types=request_content_types,
                )
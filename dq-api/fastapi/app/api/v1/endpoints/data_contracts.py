from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import Response
from fastapi.responses import JSONResponse, PlainTextResponse

from app.api.presenters.data_contracts import build_data_contract_inventory_payload
from app.api.presenters.data_contracts import build_quality_rules_payload
from app.api.presenters.data_contracts import list_contract_files
from app.api.presenters.data_contracts import normalize_data_contract_format
from app.api.presenters.data_contracts import parse_data_contract_yaml
from app.api.presenters.data_contracts import resolve_data_contract_path
from app.application.services.data_contract_governance import build_canonical_contract_snapshot
from app.application.services.data_contract_governance import diff_contract_snapshots
from app.core.dependencies import get_data_catalog_repository
from app.core.runtime_paths import find_runtime_root


router = APIRouter(tags=["data-contracts"], dependencies=[Depends(get_data_catalog_repository)])

_CONTRACTS_RELATIVE_PATH = Path("data_sources") / "contracts"


def _contracts_dir() -> Path:
    runtime_root = find_runtime_root(Path(__file__), _CONTRACTS_RELATIVE_PATH)
    candidate_dir = runtime_root / _CONTRACTS_RELATIVE_PATH
    if candidate_dir.exists() and candidate_dir.is_dir() and list_contract_files(candidate_dir):
        return candidate_dir

    for parent in Path(__file__).resolve().parents:
        fallback_dir = parent / _CONTRACTS_RELATIVE_PATH
        if fallback_dir.exists() and fallback_dir.is_dir() and list_contract_files(fallback_dir):
            return fallback_dir

    return candidate_dir


def _require_contracts_dir() -> Path:
    try:
        contracts_dir = _contracts_dir()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Data contracts directory is not available in this runtime",
        ) from exc
    if not contracts_dir.exists() or not contracts_dir.is_dir():
        raise HTTPException(
            status_code=503,
            detail="Data contracts directory is not available in this runtime",
        )
    return contracts_dir


def _contract_path_or_404(data_source_id: str) -> Path:
    contracts_dir = _require_contracts_dir()
    try:
        return resolve_data_contract_path(contracts_dir, data_source_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Data contract not found for data source: {data_source_id}",
        ) from exc


@router.get("/data-contracts")
async def list_data_contracts() -> dict[str, object]:
    contracts_dir = _require_contracts_dir()
    return build_data_contract_inventory_payload(list_contract_files(contracts_dir))


@router.get("/data-contracts/{data_source_id}")
async def get_data_contract(
    data_source_id: str,
    format: str = Query(default="yaml"),
) -> Response:
    contract_path = _contract_path_or_404(data_source_id)
    yaml_content = contract_path.read_text(encoding="utf-8")

    try:
        response_format = normalize_data_contract_format(format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unsupported format. Use 'yaml' or 'json'.") from exc

    if response_format == "json":
        try:
            parsed = parse_data_contract_yaml(yaml_content)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail="Data contract payload has invalid structure") from exc
        return JSONResponse(content=parsed)

    return PlainTextResponse(
        content=yaml_content,
        media_type="application/x-yaml",
        headers={
            "Content-Disposition": f'inline; filename="{data_source_id}.odcs.yaml"',
        },
    )


@router.get("/data-contracts/{data_source_id}/quality-rules")
async def get_quality_rules(data_source_id: str) -> dict[str, object]:
    contract_path = _contract_path_or_404(data_source_id)
    try:
        parsed = parse_data_contract_yaml(contract_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Data contract payload has invalid structure") from exc
    return build_quality_rules_payload(data_source_id, parsed)


@router.get("/data-contracts/{data_source_id}/analysis")
async def analyze_data_contract(
    data_source_id: str,
    baseline_data_source_id: str | None = None,
) -> dict[str, object]:
    contract_path = _contract_path_or_404(data_source_id)
    try:
        current_payload = parse_data_contract_yaml(contract_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Data contract payload has invalid structure") from exc

    current_snapshot = build_canonical_contract_snapshot(current_payload, data_source_id=data_source_id, source_kind="source_dataset")
    comparison = None
    if baseline_data_source_id is not None and str(baseline_data_source_id).strip():
        baseline_path = _contract_path_or_404(baseline_data_source_id)
        try:
            baseline_payload = parse_data_contract_yaml(baseline_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise HTTPException(status_code=500, detail="Baseline data contract payload has invalid structure") from exc
        baseline_snapshot = build_canonical_contract_snapshot(
            baseline_payload,
            data_source_id=baseline_data_source_id,
            source_kind="source_dataset",
        )
        comparison = diff_contract_snapshots(baseline_snapshot, current_snapshot)

    return {
        "success": True,
        "data_source_id": data_source_id,
        "contract": current_snapshot,
        "comparison": comparison,
    }

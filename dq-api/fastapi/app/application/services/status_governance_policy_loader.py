from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.domain.status_governance import get_supported_status_model_entities
from app.domain.status_governance import set_status_model_policy_overrides
from app.domain.status_governance import StatusTransitionDefinition


def _extract_status_governance_payload(source: Any) -> dict[str, Any] | None:
    if source is None:
        return None
    if hasattr(source, "statusGovernance"):
        return getattr(source, "statusGovernance")
    if isinstance(source, Mapping):
        if "statusGovernance" in source:
            return source["statusGovernance"]
        if "status_governance" in source:
            return source["status_governance"]
    return None


def _normalize_status_transition_definition(transition: Any) -> StatusTransitionDefinition:
    if not isinstance(transition, Mapping):
        if hasattr(transition, "fromStatus") and hasattr(transition, "toStatus"):
            return transition
        raise ValueError("status_governance transitions must be objects")

    payload = {
        "fromStatus": transition.get("fromStatus", transition.get("from_status")),
        "toStatus": transition.get("toStatus", transition.get("to_status")),
        "label": transition.get("label"),
        "requiredAnyScopes": transition.get("requiredAnyScopes", transition.get("required_any_scopes", [])),
    }
    return StatusTransitionDefinition.model_validate(payload)


def _build_status_model_policy_overrides(raw_policy: Any) -> dict[str, list[StatusTransitionDefinition]]:
    if not isinstance(raw_policy, Mapping):
        raise ValueError("status_governance must be an object")

    policy_overrides: dict[str, list[StatusTransitionDefinition]] = {}
    supported_entities = get_supported_status_model_entities()
    for entity_key, entity_policy in raw_policy.items():
        normalized_entity = str(entity_key or "").strip().lower()
        if normalized_entity not in supported_entities:
            raise ValueError(f"status_governance.{entity_key} is not supported")
        if entity_policy is None:
            continue
        if not isinstance(entity_policy, Mapping):
            raise ValueError(f"status_governance.{normalized_entity} must be an object")

        unexpected_keys = sorted(set(entity_policy.keys()) - {"transitions"})
        if unexpected_keys:
            raise ValueError(
                f"status_governance.{normalized_entity} includes unsupported keys: {', '.join(unexpected_keys)}"
            )

        raw_transitions = entity_policy.get("transitions")
        if raw_transitions is None:
            continue
        if not isinstance(raw_transitions, list):
            raise ValueError(f"status_governance.{normalized_entity}.transitions must be a list")

        policy_overrides[normalized_entity] = [
            _normalize_status_transition_definition(transition) for transition in raw_transitions
        ]

    return policy_overrides


def set_status_model_policy_from_source(source: Any) -> None:
    raw_policy = _extract_status_governance_payload(source)
    if raw_policy is None:
        set_status_model_policy_overrides(None)
        return

    set_status_model_policy_overrides(_build_status_model_policy_overrides(raw_policy))
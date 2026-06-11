from __future__ import annotations


RUN_PLAN_VERSION_PENDING_STATES = {
    "draft",
    "pending_validation",
    "validation_failed",
    "pending_review",
    "approved_pending_activation",
    "activation-requested",
    "deactivation-requested",
}

RUN_PLAN_VERSION_ALLOWED_TRANSITIONS = {
    "draft": {"pending_validation", "activation-requested"},
    "validation_failed": {"pending_validation", "cancelled"},
    "pending_validation": {"validation_failed", "pending_review", "approved_pending_activation"},
    "pending_review": {"approved_pending_activation", "cancelled"},
    "approved_pending_activation": {"cancelled"},
    "inactive": {"activation-requested"},
    "active": {"deactivation-requested"},
    "activation-requested": {"approved_pending_activation", "inactive"},
    "deactivation-requested": {"deactivated", "active"},
}


def is_run_plan_version_pending_state(state: str | None) -> bool:
    return str(state or "").strip() in RUN_PLAN_VERSION_PENDING_STATES


def is_valid_run_plan_version_transition(current_state: str, target_state: str) -> bool:
    return str(target_state or "").strip() in RUN_PLAN_VERSION_ALLOWED_TRANSITIONS.get(str(current_state or "").strip(), set())
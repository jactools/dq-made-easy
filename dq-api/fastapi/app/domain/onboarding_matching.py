"""Matching logic for onboarding rule suggestions."""

from __future__ import annotations

import re
from typing import NamedTuple


class TemplateMatch(NamedTuple):
    """A matched template for an attribute."""

    template_id: str
    template_name: str
    dimension: str
    check_type: str
    default_risk_level: str


# Define the DAMA template library with check types
DAMA_TEMPLATES_REGISTRY = [
    # COMPLETENESS
    TemplateMatch(
        template_id="template-completeness-1",
        template_name="NULL Value Check",
        dimension="completeness",
        check_type="THRESHOLD",
        default_risk_level="high",
    ),
    TemplateMatch(
        template_id="template-completeness-2",
        template_name="Empty String Check",
        dimension="completeness",
        check_type="THRESHOLD",
        default_risk_level="medium",
    ),
    TemplateMatch(
        template_id="template-completeness-3",
        template_name="Default Value Detection",
        dimension="completeness",
        check_type="THRESHOLD",
        default_risk_level="low",
    ),
    # ACCURACY
    TemplateMatch(
        template_id="template-accuracy-1",
        template_name="Format Validation",
        dimension="accuracy",
        check_type="REGEX",
        default_risk_level="medium",
    ),
    TemplateMatch(
        template_id="template-accuracy-2",
        template_name="Email Format Check",
        dimension="accuracy",
        check_type="REGEX",
        default_risk_level="high",
    ),
    TemplateMatch(
        template_id="template-accuracy-3",
        template_name="Phone Number Validation",
        dimension="accuracy",
        check_type="REGEX",
        default_risk_level="medium",
    ),
    TemplateMatch(
        template_id="template-accuracy-4",
        template_name="Allowlist Validation",
        dimension="accuracy",
        check_type="ALLOWLIST",
        default_risk_level="high",
    ),
    # CONSISTENCY
    TemplateMatch(
        template_id="template-consistency-1",
        template_name="Referential Integrity",
        dimension="consistency",
        check_type="REFERENTIAL_INTEGRITY",
        default_risk_level="high",
    ),
    # TIMELINESS
    TemplateMatch(
        template_id="template-timeliness-1",
        template_name="Freshness Check",
        dimension="timeliness",
        check_type="FRESHNESS",
        default_risk_level="high",
    ),
    TemplateMatch(
        template_id="template-timeliness-2",
        template_name="Lag Detection",
        dimension="timeliness",
        check_type="LAG",
        default_risk_level="medium",
    ),
    TemplateMatch(
        template_id="template-timeliness-3",
        template_name="Future Date Detection",
        dimension="timeliness",
        check_type="FUTURE_DATE",
        default_risk_level="high",
    ),
    # VALIDITY
    TemplateMatch(
        template_id="template-validity-1",
        template_name="Range Check",
        dimension="validity",
        check_type="RANGE",
        default_risk_level="medium",
    ),
    # UNIQUENESS
    TemplateMatch(
        template_id="template-uniqueness-1",
        template_name="Uniqueness",
        dimension="uniqueness",
        check_type="UNIQUENESS",
        default_risk_level="medium",
    ),
]


def match_templates_to_attribute(
    *,
    attribute_name: str,
    data_type: str,
    is_required: bool = False,
) -> list[TemplateMatch]:
    """Match applicable templates to an attribute based on metadata signals.
    
    Args:
        attribute_name: The attribute name (used for pattern matching)
        data_type: The attribute data type (string, numeric, date, boolean, etc.)
        is_required: Whether the attribute is marked as required/non-nullable
        
    Returns:
        A list of matched templates in priority order
    """
    matches = []
    normalized_name = attribute_name.lower()

    # Universal baseline: NULL Value Check applies to all attributes
    null_check = next(
        (t for t in DAMA_TEMPLATES_REGISTRY if t.template_id == "template-completeness-1"),
        None,
    )
    if null_check:
        matches.append(null_check)
    
    # Boost severity if attribute is required
    if is_required and matches:
        # Risk level already set to 'high' for NULL Value Check, so no need to override
        pass

    # String/text type: Empty String Check
    if data_type.lower() in ("string", "text", "varchar", "char"):
        empty_check = next(
            (t for t in DAMA_TEMPLATES_REGISTRY if t.template_id == "template-completeness-2"),
            None,
        )
        if empty_check:
            matches.append(empty_check)

    # Date/time patterns
    if re.search(r"(_date|_at|_time)$", normalized_name):
        # Freshness Check
        freshness = next(
            (t for t in DAMA_TEMPLATES_REGISTRY if t.template_id == "template-timeliness-1"),
            None,
        )
        if freshness:
            matches.append(freshness)
        
        # Future Date Detection
        future_date = next(
            (t for t in DAMA_TEMPLATES_REGISTRY if t.template_id == "template-timeliness-3"),
            None,
        )
        if future_date:
            matches.append(future_date)

    # ID/Key/Code patterns: suggest Uniqueness
    if re.search(r"(_id|_key|_code)$", normalized_name):
        uniqueness = next(
            (t for t in DAMA_TEMPLATES_REGISTRY if t.template_id == "template-uniqueness-1"),
            None,
        )
        if uniqueness:
            matches.append(uniqueness)

    # Email pattern
    if normalized_name in ("email", "email_address") or normalized_name.endswith("_email"):
        email_check = next(
            (t for t in DAMA_TEMPLATES_REGISTRY if t.template_id == "template-accuracy-2"),
            None,
        )
        if email_check:
            matches.append(email_check)

    # Phone pattern
    if normalized_name in ("phone", "phone_number") or normalized_name.endswith(
        "_phone"
    ):
        phone_check = next(
            (t for t in DAMA_TEMPLATES_REGISTRY if t.template_id == "template-accuracy-3"),
            None,
        )
        if phone_check:
            matches.append(phone_check)

    # Numeric type: Range Check
    if data_type.lower() in (
        "numeric",
        "decimal",
        "int",
        "integer",
        "bigint",
        "float",
        "double",
    ):
        range_check = next(
            (t for t in DAMA_TEMPLATES_REGISTRY if t.template_id == "template-validity-1"),
            None,
        )
        if range_check:
            matches.append(range_check)

    # Deduplicate and preserve order
    seen = set()
    deduped = []
    for match in matches:
        if match.template_id not in seen:
            seen.add(match.template_id)
            deduped.append(match)

    return deduped

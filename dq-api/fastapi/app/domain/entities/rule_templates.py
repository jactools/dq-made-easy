from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import Field

from app.domain.entities.base import EntityModel


def _merge_mapping(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_mapping(dict(merged[key]), value)
        else:
            merged[key] = deepcopy(value)
    return merged


class RuleTemplatePackEntity(EntityModel):
    id: str
    name: str
    description: str
    dimension: str
    template_ids: list[str] = Field(default_factory=list)
    default_template_rule_definition: dict[str, Any] = Field(default_factory=dict)


class RuleTemplateEntity(EntityModel):
    id: str
    name: str
    description: str
    dimension: str
    category: str
    default_risk_level: str
    rule_type: str
    template_rule_definition: dict[str, Any] = Field(default_factory=dict)
    example_use: str
    icon: str | None = None
    pack_id: str
    pack_name: str | None = None
    inherits_from_template_id: str | None = None
    parameter_schema: list[dict[str, Any]] = Field(default_factory=list)
    inheritance_chain: list[str] = Field(default_factory=list)


class RuleTemplateResolutionEntity(EntityModel):
    template: RuleTemplateEntity
    pack: RuleTemplatePackEntity
    inheritance_chain: list[str] = Field(default_factory=list)
    applied_overrides: dict[str, Any] = Field(default_factory=dict)


_RULE_TEMPLATE_PACKS: tuple[RuleTemplatePackEntity, ...] = (
    RuleTemplatePackEntity(
        id="pack-presence",
        name="Presence controls",
        description="Reusable completeness controls for missing, blank, and placeholder data.",
        dimension="completeness",
        template_ids=[
            "template-completeness-1",
            "template-completeness-2",
            "template-completeness-3",
        ],
        default_template_rule_definition={"operator": "percentage_over"},
    ),
    RuleTemplatePackEntity(
        id="pack-conformance",
        name="Format conformance",
        description="Parameterized format checks for pattern and value conformance.",
        dimension="accuracy",
        template_ids=[
            "template-accuracy-1",
            "template-accuracy-2",
            "template-accuracy-3",
        ],
        default_template_rule_definition={"operator": "regex"},
    ),
    RuleTemplatePackEntity(
        id="pack-consistency",
        name="Cross-system consistency",
        description="Shared comparison contracts for referential integrity and reconciliation reuse.",
        dimension="consistency",
        template_ids=[
            "template-consistency-1",
            "template-consistency-2",
            "template-reconciliation-1",
        ],
        default_template_rule_definition={"operator": "custom"},
    ),
    RuleTemplatePackEntity(
        id="pack-timeliness",
        name="Freshness and lag",
        description="Templates for freshness, pipeline lag, and future-dated records.",
        dimension="timeliness",
        template_ids=[
            "template-timeliness-1",
            "template-timeliness-2",
            "template-timeliness-3",
        ],
        default_template_rule_definition={"operator": "range"},
    ),
    RuleTemplatePackEntity(
        id="pack-validity",
        name="Validity checks",
        description="Range and boundary controls for accepted business values.",
        dimension="validity",
        template_ids=[
            "template-validity-1",
            "template-validity-2",
            "template-validity-3",
            "template-validity-4",
            "template-validity-5",
            "template-validity-6",
            "template-validity-7",
        ],
        default_template_rule_definition={"operator": "range"},
    ),
    RuleTemplatePackEntity(
        id="pack-uniqueness",
        name="Uniqueness controls",
        description="Reusable controls for deduplication, key integrity, and key-based checks.",
        dimension="uniqueness",
        template_ids=[
            "template-uniqueness-1",
            "template-uniqueness-2",
            "template-uniqueness-3",
        ],
        default_template_rule_definition={"operator": "custom"},
    ),
)


_RULE_TEMPLATES: tuple[RuleTemplateEntity, ...] = (
    RuleTemplateEntity(
        id="template-completeness-1",
        name="NULL Value Check",
        description="Detect rows with NULL or missing values in critical columns.",
        dimension="completeness",
        category="Data Presence",
        default_risk_level="high",
        rule_type="threshold",
        template_rule_definition={
            "description": "Check for missing values",
            "attributes": [],
            "threshold": 95,
        },
        example_use="Ensure customer email addresses are always populated.",
        icon="warning",
        pack_id="pack-presence",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Columns to inspect."},
            {"name": "threshold", "type": "number", "required": False, "description": "Minimum acceptable coverage."},
        ],
    ),
    RuleTemplateEntity(
        id="template-completeness-2",
        name="Empty String Check",
        description="Detect empty strings that should contain data.",
        dimension="completeness",
        category="Data Presence",
        default_risk_level="medium",
        rule_type="threshold",
        template_rule_definition={
            "description": "Check for empty strings",
            "attributes": [],
            "threshold": 97,
        },
        example_use="Validate product descriptions are not blank.",
        icon="dash-circle-fill",
        pack_id="pack-presence",
        inherits_from_template_id="template-completeness-1",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Columns to inspect."},
            {"name": "threshold", "type": "number", "required": False, "description": "Minimum acceptable coverage."},
        ],
    ),
    RuleTemplateEntity(
        id="template-completeness-3",
        name="Default Value Detection",
        description="Identify data defaults that may indicate incomplete data entry.",
        dimension="completeness",
        category="Data Presence",
        default_risk_level="low",
        rule_type="threshold",
        template_rule_definition={
            "description": "Check for default or placeholder values",
            "attributes": [],
            "expectedValues": {"placeholder": "N/A"},
            "threshold": 90,
        },
        example_use='Detect when house addresses are left as "Unknown".',
        icon="database",
        pack_id="pack-presence",
        inherits_from_template_id="template-completeness-1",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Columns to inspect."},
            {"name": "threshold", "type": "number", "required": False, "description": "Minimum acceptable coverage."},
            {"name": "expectedValues.placeholder", "type": "string", "required": False, "description": "Placeholder value to flag."},
        ],
    ),
    RuleTemplateEntity(
        id="template-accuracy-1",
        name="Format Validation",
        description="Verify data matches the expected format or pattern.",
        dimension="accuracy",
        category="Format Conformance",
        default_risk_level="medium",
        rule_type="regex",
        template_rule_definition={
            "description": "Pattern match validation",
            "attributes": [],
            "expectedValues": {"pattern": "^[A-Z0-9]+$"},
        },
        example_use="Ensure customer IDs match a controlled pattern.",
        icon="check-circle",
        pack_id="pack-conformance",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Columns to inspect."},
            {"name": "expectedValues.pattern", "type": "string", "required": True, "description": "Pattern to enforce."},
        ],
    ),
    RuleTemplateEntity(
        id="template-accuracy-2",
        name="Email Format Check",
        description="Validate email addresses follow RFC-style format.",
        dimension="accuracy",
        category="Format Conformance",
        default_risk_level="high",
        rule_type="regex",
        template_rule_definition={
            "description": "Email format validation",
            "attributes": [],
            "expectedValues": {"pattern": "^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$"},
        },
        example_use="Ensure all contact emails are valid formats.",
        icon="envelope",
        pack_id="pack-conformance",
        inherits_from_template_id="template-accuracy-1",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Columns to inspect."},
            {"name": "expectedValues.pattern", "type": "string", "required": True, "description": "Pattern to enforce."},
        ],
    ),
    RuleTemplateEntity(
        id="template-accuracy-3",
        name="Phone Number Validation",
        description="Verify phone numbers conform to the expected format.",
        dimension="accuracy",
        category="Format Conformance",
        default_risk_level="medium",
        rule_type="regex",
        template_rule_definition={
            "description": "Phone format validation",
            "attributes": [],
            "expectedValues": {"pattern": "^\\+?[0-9]{10,}$"},
        },
        example_use="Validate phone numbers have the correct digit count.",
        icon="phone",
        pack_id="pack-conformance",
        inherits_from_template_id="template-accuracy-1",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Columns to inspect."},
            {"name": "expectedValues.pattern", "type": "string", "required": True, "description": "Pattern to enforce."},
        ],
    ),
    RuleTemplateEntity(
        id="template-consistency-1",
        name="Referential Integrity",
        description="Verify foreign key references exist in the parent table.",
        dimension="consistency",
        category="Cross-Table Consistency",
        default_risk_level="high",
        rule_type="custom",
        template_rule_definition={
            "description": "Check referential integrity",
            "attributes": [],
            "expectedValues": {"parentTable": "parent_table", "foreignKey": "parent_id"},
        },
        example_use="Ensure all order.customer_id values exist in customers.id.",
        icon="link",
        pack_id="pack-consistency",
        parameter_schema=[
            {"name": "expectedValues.parentTable", "type": "string", "required": True, "description": "Referenced table name."},
            {"name": "expectedValues.foreignKey", "type": "string", "required": True, "description": "Foreign key column to enforce."},
        ],
    ),
    RuleTemplateEntity(
        id="template-consistency-2",
        name="Cross Dataset Integrity",
        description="Compare shared business keys across related datasets and flag diverging values.",
        dimension="consistency",
        category="Cross-System Comparison",
        default_risk_level="high",
        rule_type="custom",
        template_rule_definition={
            "description": "Check cross-dataset integrity",
            "attributes": [],
            "expectedValues": {
                "joinKeys": [{"leftAttribute": "customer_id", "rightAttribute": "customer_id"}],
                "comparisonColumns": [
                    {"leftAttribute": "status", "rightAttribute": "status", "mode": "exact"}
                ],
            },
        },
        example_use="Verify account status stays aligned between operational and reporting datasets.",
        icon="shuffle",
        pack_id="pack-consistency",
        inherits_from_template_id="template-consistency-1",
        parameter_schema=[
            {"name": "expectedValues.joinKeys", "type": "array", "required": True, "description": "Join-key mapping used for the comparison."},
            {"name": "expectedValues.comparisonColumns", "type": "array", "required": True, "description": "Columns that must remain synchronized."},
        ],
    ),
    RuleTemplateEntity(
        id="template-reconciliation-1",
        name="Reconciliation Blueprint",
        description="Reusable left/right comparison contract for Data Assets and rules.",
        dimension="consistency",
        category="Cross-System Comparison",
        default_risk_level="high",
        rule_type="custom",
        template_rule_definition={
            "description": "Reusable reconciliation definition",
            "leftDataObjectVersionId": "ledger-left-v1",
            "rightDataObjectVersionId": "ledger-right-v1",
            "joinKeys": [{"leftAttribute": "account_id", "rightAttribute": "account_id"}],
            "comparisons": [
                {"leftAttribute": "status", "rightAttribute": "status", "mode": "exact"},
                {"leftAttribute": "balance_amount", "rightAttribute": "balance_amount", "mode": "numeric_tolerance", "tolerance": 0.01},
            ],
            "reusableTargets": ["rules", "data_assets"],
        },
        example_use="Reuse the same left/right comparison blueprint in rule authoring and policy documents.",
        icon="link",
        pack_id="pack-consistency",
        inherits_from_template_id="template-consistency-1",
        parameter_schema=[
            {"name": "leftDataObjectVersionId", "type": "string", "required": True, "description": "Left-hand source version."},
            {"name": "rightDataObjectVersionId", "type": "string", "required": True, "description": "Right-hand source version."},
            {"name": "joinKeys", "type": "array", "required": True, "description": "Join-key mapping used by the comparison."},
        ],
    ),
    RuleTemplateEntity(
        id="template-timeliness-1",
        name="Freshness Check",
        description="Verify data is updated within the expected time window.",
        dimension="timeliness",
        category="Data Currency",
        default_risk_level="high",
        rule_type="range",
        template_rule_definition={
            "description": "Check data freshness",
            "attributes": ["updated_at"],
            "expectedValues": {"maxDaysOld": 7},
        },
        example_use="Ensure customer records are updated at least weekly.",
        icon="clock",
        pack_id="pack-timeliness",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Timestamp columns to inspect."},
            {"name": "expectedValues.maxDaysOld", "type": "number", "required": True, "description": "Maximum age allowed in days."},
        ],
    ),
    RuleTemplateEntity(
        id="template-timeliness-2",
        name="Processing Lag Detection",
        description="Monitor delay between data creation and processing.",
        dimension="timeliness",
        category="Data Currency",
        default_risk_level="medium",
        rule_type="range",
        template_rule_definition={
            "description": "Check processing lag",
            "attributes": ["created_at", "processed_at"],
            "expectedValues": {"maxHoursLag": 24},
        },
        example_use="Ensure transactions are processed within 24 hours.",
        icon="warning",
        pack_id="pack-timeliness",
        inherits_from_template_id="template-timeliness-1",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Timestamp columns to inspect."},
            {"name": "expectedValues.maxHoursLag", "type": "number", "required": True, "description": "Maximum processing lag in hours."},
        ],
    ),
    RuleTemplateEntity(
        id="template-timeliness-3",
        name="Future Date Detection",
        description="Flag records with dates in the future.",
        dimension="timeliness",
        category="Date Validity",
        default_risk_level="high",
        rule_type="custom",
        template_rule_definition={
            "description": "Check for future dates",
            "attributes": ["event_date"],
            "expectedValues": {"maxDaysAhead": 0},
        },
        example_use="Reject event dates that occur after the reporting window.",
        icon="calendar",
        pack_id="pack-timeliness",
        inherits_from_template_id="template-timeliness-1",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Date columns to inspect."},
            {"name": "expectedValues.maxDaysAhead", "type": "number", "required": True, "description": "Maximum number of future days allowed."},
        ],
    ),
    RuleTemplateEntity(
        id="template-validity-1",
        name="Range Check",
        description="Verify numeric or date values stay within approved bounds.",
        dimension="validity",
        category="Boundary Validation",
        default_risk_level="medium",
        rule_type="range",
        template_rule_definition={
            "description": "Check numeric or date ranges",
            "attributes": ["amount"],
            "expectedValues": {"minimum": 0, "maximum": 1000},
        },
        example_use="Keep invoice totals inside approved financial bounds.",
        icon="info-circle",
        pack_id="pack-validity",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Columns to inspect."},
            {"name": "expectedValues.minimum", "type": "number", "required": False, "description": "Lower bound allowed."},
            {"name": "expectedValues.maximum", "type": "number", "required": False, "description": "Upper bound allowed."},
        ],
    ),
    RuleTemplateEntity(
        id="template-validity-2",
        name="Age Validation",
        description="Ensure ages or similar values remain within human bounds.",
        dimension="validity",
        category="Boundary Validation",
        default_risk_level="high",
        rule_type="range",
        template_rule_definition={
            "description": "Validate age range",
            "attributes": ["age"],
            "expectedValues": {"minimum": 18, "maximum": 120},
        },
        example_use="Reject ages outside realistic operational bounds.",
        icon="person",
        pack_id="pack-validity",
        inherits_from_template_id="template-validity-1",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Columns to inspect."},
            {"name": "expectedValues.minimum", "type": "number", "required": False, "description": "Lower bound allowed."},
            {"name": "expectedValues.maximum", "type": "number", "required": False, "description": "Upper bound allowed."},
        ],
    ),
    RuleTemplateEntity(
        id="template-validity-3",
        name="Outlier Detection",
        description="Flag outlier values that fall too far from the expected range.",
        dimension="validity",
        category="Boundary Validation",
        default_risk_level="low",
        rule_type="range",
        template_rule_definition={
            "description": "Flag outlier values",
            "attributes": ["score"],
            "expectedValues": {"minimum": 0, "maximum": 100, "outlierDeviation": 3},
        },
        example_use="Detect suspicious scores or amounts before publication.",
        icon="graph-up",
        pack_id="pack-validity",
        inherits_from_template_id="template-validity-1",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Columns to inspect."},
            {"name": "expectedValues.outlierDeviation", "type": "number", "required": False, "description": "Standard-deviation threshold for outlier flagging."},
        ],
    ),
    RuleTemplateEntity(
        id="template-validity-4",
        name="Distribution Drift",
        description="Detect shifts in a value distribution against a historical baseline.",
        dimension="validity",
        category="Statistical Validation",
        default_risk_level="medium",
        rule_type="custom",
        template_rule_definition={
            "description": "Check distribution drift",
            "attributes": ["amount"],
            "expectedValues": {"baselineWindow": "30d", "distributionMetric": "psi", "driftThreshold": 0.2},
        },
        example_use="Flag unexpected shifts in transaction amounts after a release.",
        icon="graph-up",
        pack_id="pack-validity",
        inherits_from_template_id="template-validity-3",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Columns to inspect."},
            {"name": "expectedValues.baselineWindow", "type": "string", "required": True, "description": "Lookback window for the baseline distribution."},
            {"name": "expectedValues.driftThreshold", "type": "number", "required": True, "description": "Maximum acceptable drift score."},
        ],
    ),
    RuleTemplateEntity(
        id="template-validity-5",
        name="Entropy Drift",
        description="Track entropy changes that indicate categorical instability.",
        dimension="validity",
        category="Statistical Validation",
        default_risk_level="medium",
        rule_type="custom",
        template_rule_definition={
            "description": "Check entropy drift",
            "attributes": ["status"],
            "expectedValues": {"baselineWindow": "14d", "entropyThreshold": 0.15},
        },
        example_use="Detect sudden label churn in workflow statuses.",
        icon="activity",
        pack_id="pack-validity",
        inherits_from_template_id="template-validity-4",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Columns to inspect."},
            {"name": "expectedValues.baselineWindow", "type": "string", "required": True, "description": "Lookback window for the entropy baseline."},
            {"name": "expectedValues.entropyThreshold", "type": "number", "required": True, "description": "Maximum acceptable entropy drift."},
        ],
    ),
    RuleTemplateEntity(
        id="template-validity-6",
        name="Probabilistic Threshold",
        description="Validate probabilistic scores stay above an agreed confidence floor.",
        dimension="validity",
        category="Statistical Validation",
        default_risk_level="high",
        rule_type="custom",
        template_rule_definition={
            "description": "Check probabilistic threshold",
            "attributes": ["risk_score"],
            "expectedValues": {"confidenceLevel": 0.99, "minimumProbability": 0.95},
        },
        example_use="Only publish records when the classifier confidence is high enough.",
        icon="percent",
        pack_id="pack-validity",
        inherits_from_template_id="template-validity-5",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Columns to inspect."},
            {"name": "expectedValues.confidenceLevel", "type": "number", "required": True, "description": "Confidence level required for acceptance."},
            {"name": "expectedValues.minimumProbability", "type": "number", "required": True, "description": "Minimum probability required for acceptance."},
        ],
    ),
    RuleTemplateEntity(
        id="template-validity-7",
        name="Seasonality Stability",
        description="Ensure repeating seasonal patterns stay within the expected variation band.",
        dimension="validity",
        category="Statistical Validation",
        default_risk_level="medium",
        rule_type="custom",
        template_rule_definition={
            "description": "Check seasonality stability",
            "attributes": ["sales_amount"],
            "expectedValues": {"baselineWindow": "28d", "maxDeviation": 0.1, "seasonalPeriod": "7d"},
        },
        example_use="Detect week-over-week spikes that break the normal weekly pattern.",
        icon="calendar",
        pack_id="pack-validity",
        inherits_from_template_id="template-validity-6",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Columns to inspect."},
            {"name": "expectedValues.baselineWindow", "type": "string", "required": True, "description": "Lookback window for the seasonal baseline."},
            {"name": "expectedValues.maxDeviation", "type": "number", "required": True, "description": "Maximum acceptable deviation from the seasonal baseline."},
        ],
    ),
    RuleTemplateEntity(
        id="template-uniqueness-1",
        name="Primary Key Check",
        description="Ensure the selected key fields remain unique.",
        dimension="uniqueness",
        category="Key Integrity",
        default_risk_level="high",
        rule_type="custom",
        template_rule_definition={
            "description": "Check primary key uniqueness",
            "attributes": ["id"],
            "expectedValues": {"keyFields": ["id"]},
        },
        example_use="Guarantee the business key never duplicates within a dataset.",
        icon="key",
        pack_id="pack-uniqueness",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Columns that should remain unique."},
            {"name": "expectedValues.keyFields", "type": "array", "required": True, "description": "Fields that define uniqueness."},
        ],
    ),
    RuleTemplateEntity(
        id="template-uniqueness-2",
        name="Duplicate Detection",
        description="Detect duplicate records across the selected key fields.",
        dimension="uniqueness",
        category="Key Integrity",
        default_risk_level="medium",
        rule_type="custom",
        template_rule_definition={
            "description": "Detect duplicate records",
            "attributes": ["email"],
            "expectedValues": {"keyFields": ["email"]},
        },
        example_use="Ensure duplicate contact records are not introduced.",
        icon="layers",
        pack_id="pack-uniqueness",
        inherits_from_template_id="template-uniqueness-1",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Columns that should remain unique."},
            {"name": "expectedValues.keyFields", "type": "array", "required": True, "description": "Fields that define uniqueness."},
        ],
    ),
    RuleTemplateEntity(
        id="template-uniqueness-3",
        name="Email Uniqueness",
        description="Ensure email addresses appear only once in the controlled dataset.",
        dimension="uniqueness",
        category="Key Integrity",
        default_risk_level="high",
        rule_type="regex",
        template_rule_definition={
            "description": "Validate email uniqueness",
            "attributes": ["email"],
            "expectedValues": {"keyFields": ["email"], "pattern": "^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$"},
        },
        example_use="Prevent the same contact email from being reused across customer records.",
        icon="envelope",
        pack_id="pack-uniqueness",
        inherits_from_template_id="template-uniqueness-1",
        parameter_schema=[
            {"name": "attributes", "type": "array", "required": True, "description": "Columns that should remain unique."},
            {"name": "expectedValues.keyFields", "type": "array", "required": True, "description": "Fields that define uniqueness."},
            {"name": "expectedValues.pattern", "type": "string", "required": False, "description": "Optional pattern used by downstream previews."},
        ],
    ),
)


_RULE_TEMPLATE_PACKS_BY_ID = {pack.id: pack for pack in _RULE_TEMPLATE_PACKS}
_RULE_TEMPLATES_BY_ID = {template.id: template for template in _RULE_TEMPLATES}


def _resolve_template(template_id: str, overrides: dict[str, Any] | None = None) -> RuleTemplateResolutionEntity:
    template = _RULE_TEMPLATES_BY_ID.get(template_id)
    if template is None:
        raise LookupError(f"Template '{template_id}' not found")

    pack = _RULE_TEMPLATE_PACKS_BY_ID.get(template.pack_id)
    if pack is None:
        raise LookupError(f"Template pack '{template.pack_id}' not found")

    resolved_definition = deepcopy(pack.default_template_rule_definition)
    inheritance_chain: list[str] = []

    if template.inherits_from_template_id:
        parent_resolution = _resolve_template(template.inherits_from_template_id)
        resolved_definition = _merge_mapping(resolved_definition, parent_resolution.template.template_rule_definition)
        inheritance_chain.extend(parent_resolution.inheritance_chain)

    resolved_definition = _merge_mapping(resolved_definition, template.template_rule_definition)

    applied_overrides = deepcopy(overrides or {})
    if applied_overrides:
        resolved_definition = _merge_mapping(resolved_definition, applied_overrides)

    inheritance_chain.append(template.id)

    resolved_template = template.model_copy(
        update={
            "pack_name": pack.name,
            "template_rule_definition": resolved_definition,
            "inheritance_chain": inheritance_chain,
        }
    )

    return RuleTemplateResolutionEntity(
        template=resolved_template,
        pack=pack,
        inheritance_chain=inheritance_chain,
        applied_overrides=applied_overrides,
    )


def list_rule_template_packs() -> list[RuleTemplatePackEntity]:
    return [pack.model_copy(deep=True) for pack in _RULE_TEMPLATE_PACKS]


def list_rule_templates(pack_id: str | None = None, dimension: str | None = None) -> list[RuleTemplateEntity]:
    packs = list_rule_template_packs()
    pack_lookup = {pack.id: pack for pack in packs}

    if pack_id is not None and pack_id.strip() and pack_id not in pack_lookup:
        raise LookupError(f"Template pack '{pack_id}' not found")

    templates: list[RuleTemplateEntity] = []
    for template in _RULE_TEMPLATES:
        if pack_id is not None and pack_id.strip() and template.pack_id != pack_id:
            continue
        if dimension is not None and dimension.strip() and template.dimension != dimension:
            continue
        resolution = _resolve_template(template.id)
        templates.append(resolution.template)
    return templates


def resolve_rule_template(template_id: str, overrides: dict[str, Any] | None = None) -> RuleTemplateResolutionEntity:
    return _resolve_template(template_id, overrides)


__all__ = [
    "RuleTemplateEntity",
    "RuleTemplatePackEntity",
    "RuleTemplateResolutionEntity",
    "list_rule_template_packs",
    "list_rule_templates",
    "resolve_rule_template",
]
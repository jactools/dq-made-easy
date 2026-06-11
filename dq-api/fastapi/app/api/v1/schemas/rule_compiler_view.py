from typing import Any

from pydantic import Field

from dq_domain_validation import RuleCompilerCompilerVersioning
from dq_domain_validation import RuleCompilerEngineTarget
from dq_domain_validation import RuleCompilerInputFormat
from dq_domain_validation import RuleCompilerLogicalOperator
from dq_domain_validation import RuleCompilerSchemaVersioning
from dq_domain_validation import RuleCompilerSeverity
from dq_domain_validation import RuleCompilerSupportedSchemaSeries
from dq_domain_validation import RuleCompilerTarget
from app.schemas.pydantic_base import SnakeModel


class CompilerDiagnosticView(SnakeModel):
    code: str
    severity: RuleCompilerSeverity
    message: str
    scope: str = "rule"


class CompilerPredicateView(SnakeModel):
    field: str
    operator: str
    value: str
    valueType: str


class CompilerAliasExpectationView(SnakeModel):
    alias: str
    expected: str


class CompilerRuleReferenceView(SnakeModel):
    id: str
    versionId: str


class RuleFilterIntermediateView(SnakeModel):
    source: str
    normalized: str
    predicates: list[CompilerPredicateView] = Field(default_factory=list)
    logicalOperators: list[RuleCompilerLogicalOperator] = Field(default_factory=list)
    aliasExpectations: list[CompilerAliasExpectationView] = Field(default_factory=list)
    ast: dict[str, Any] | None = None


class CompilerExecutionTraceabilityView(SnakeModel):
    ruleId: str
    ruleVersionId: str
    artifactKey: str
    compilerVersion: str = Field(pattern=r"^dq-\d+\.\d+\.\d+$")
    schemaVersion: str = Field(pattern=r"^\d+\.\d+\.\d+$")


class CompilerCompatibilityPolicyView(SnakeModel):
    schemaVersioning: RuleCompilerSchemaVersioning
    compilerVersioning: RuleCompilerCompilerVersioning
    supportedSchemaSeries: RuleCompilerSupportedSchemaSeries
    minorVersionBackwardCompatible: bool


class CompilerExecutionContractView(SnakeModel):
    engineTarget: RuleCompilerEngineTarget
    inputFormat: RuleCompilerInputFormat
    compatibilityPolicy: CompilerCompatibilityPolicyView
    traceability: CompilerExecutionTraceabilityView
    requiredExecutionResultFields: list[str] = Field(default_factory=list)


class RuleIntermediateModelView(SnakeModel):
    artifactKey: str
    compilerVersion: str = Field(pattern=r"^dq-\d+\.\d+\.\d+$")
    schemaVersion: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    target: RuleCompilerTarget
    rule: CompilerRuleReferenceView
    filter: RuleFilterIntermediateView
    join: list[dict[str, Any]] | dict[str, Any] | None = None
    executionContract: CompilerExecutionContractView
    diagnostics: list[CompilerDiagnosticView] = Field(default_factory=list)
    compilable: bool


class RuleValidationSummaryView(SnakeModel):
    errors: int
    warnings: int


class ValidationPolicyView(SnakeModel):
    checkId: str
    enabled: bool = True
    severityOverride: RuleCompilerSeverity | None = None
    scope: str = "all"


class RuleValidationResponseView(SnakeModel):
    valid: bool
    compiledExpression: str
    inferredAliases: list[CompilerAliasExpectationView] = Field(default_factory=list)
    artifactKey: str
    compilerVersion: str = Field(pattern=r"^dq-\d+\.\d+\.\d+$")
    target: RuleCompilerTarget
    intermediateModel: RuleIntermediateModelView
    summary: RuleValidationSummaryView
    diagnostics: list[CompilerDiagnosticView] = Field(default_factory=list)


class ConflictDiagnosticView(SnakeModel):
    ruleId: str
    conflictsWith: str
    conflictType: str
    message: str


class BatchValidationResultItemView(SnakeModel):
    ruleId: str
    ruleName: str | None = None
    valid: bool
    compiledExpression: str
    artifactKey: str | None = None
    compilerVersion: str | None = None
    errors: int
    warnings: int
    diagnostics: list[CompilerDiagnosticView] = Field(default_factory=list)


class BatchValidationSummaryView(SnakeModel):
    total: int
    valid: int
    invalid: int
    errors: int
    warnings: int


class BatchValidationRequestView(SnakeModel):
    ruleIds: list[str]
    workspace: str | None = None


class BatchValidationResponseView(SnakeModel):
    runId: str
    results: list[BatchValidationResultItemView] = Field(default_factory=list)
    conflicts: list[ConflictDiagnosticView] = Field(default_factory=list)
    summary: BatchValidationSummaryView


class ValidationRunItemView(SnakeModel):
    id: str
    ruleId: str
    ruleName: str | None = None
    ruleVersionNumber: int | None = None
    valid: bool
    errors: int
    warnings: int
    diagnostics: list[CompilerDiagnosticView] = Field(default_factory=list)
    conflicts: list[ConflictDiagnosticView] = Field(default_factory=list)


class ValidationRunView(SnakeModel):
    id: str
    workspace: str | None = None
    triggeredBy: str | None = None
    runAt: str
    total: int
    validCount: int
    invalidCount: int
    status: str
    items: list[ValidationRunItemView] = Field(default_factory=list)


class ValidationRunsPageView(SnakeModel):
    data: list[ValidationRunView] = Field(default_factory=list)
    pagination: dict[str, Any]

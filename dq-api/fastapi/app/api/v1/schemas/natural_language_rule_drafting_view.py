from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import Field

from app.domain.entities.rule_dsl_v2 import RuleDslV2Document
from app.schemas.pydantic_base import SnakeModel


class NaturalLanguageRulePreviewRequestView(SnakeModel):
	prompt: str = Field(min_length=1)
	searchScope: Literal["current", "all", "all_across_workspaces"] = "current"
	currentWorkspaceId: str = Field(min_length=1)
	analysisProvider: Literal["rapidfuzz", "llm"] = "rapidfuzz"
	assistantMode: Literal["preview", "steward"] = "preview"
	targetType: Literal["data_object_version", "glossary_term"] | None = None
	targetId: str | None = None


class NaturalLanguageRulePreviewCreateSuggestionRequestView(NaturalLanguageRulePreviewRequestView):
	selectedAttributeIds: list[str] = Field(default_factory=list)


class NaturalLanguageDraftRequestStatusView(SnakeModel):
	requestId: str
	currentWorkspaceId: str
	searchScope: Literal["current", "all", "all_across_workspaces"]
	analysisProvider: Literal["rapidfuzz", "llm"]
	analysisType: Literal["preview", "draft", "steward"]
	selectedAttributeIds: list[str] = Field(default_factory=list)
	prompt: str
	requestedByUserId: str | None = None
	requestedAt: str | None = None
	startedAt: str | None = None
	completedAt: str | None = None
	status: Literal["pending", "started", "completed", "failed"]
	errorMessage: str | None = None
	suggestionId: str | None = None
	jobId: str | None = None
	result: dict[str, Any] | None = None


class NaturalLanguageDraftRequestStatusResponseView(SnakeModel):
	success: bool = True
	request: NaturalLanguageDraftRequestStatusView


class NaturalLanguageDraftRequestHistoryResponseView(SnakeModel):
	success: bool = True
	requests: list[NaturalLanguageDraftRequestStatusView] = Field(default_factory=list)
	count: int = 0


class NaturalLanguageDraftSuggestionResponseView(SnakeModel):
	success: bool = True
	queued: bool = False
	message: str
	requestId: str | None = None
	suggestion: dict[str, Any] | None = None


class NaturalLanguagePreviewCandidateView(SnakeModel):
	attributeId: str
	attributeName: str
	versionId: str
	dataObjectId: str
	dataObjectName: str
	dataSetId: str
	dataSetName: str
	dataProductId: str
	dataProductName: str
	workspaceId: str
	parentPath: list[str]
	confidenceScore: float
	matchReasons: list[str] = Field(default_factory=list)
	currentContext: bool = False
	matchRoles: list[str] = Field(default_factory=list)


class NaturalLanguageParsedConditionView(SnakeModel):
	attributeTerm: str
	operator: str
	value: str
	sameVersionRequired: bool = True


class NaturalLanguageDraftRulePreviewView(SnakeModel):
	name: str
	workspaceId: str
	dimension: str
	summary: str
	dsl: RuleDslV2Document


class NaturalLanguageRulePreviewResponseView(SnakeModel):
	success: bool = True
	queued: bool = False
	requestId: str | None = None
	message: str | None = None
	assistantMode: Literal["preview", "steward"] = "preview"
	targetType: Literal["data_object_version", "glossary_term"] | None = None
	targetId: str | None = None
	targetLabel: str | None = None
	metadataSummary: str | None = None
	explanation: str | None = None
	suggestedFixes: list[str] = Field(default_factory=list)
	metadataFacts: dict[str, Any] = Field(default_factory=dict)
	targetTerms: list[str] = Field(default_factory=list)
	searchScope: Literal["current", "all", "all_across_workspaces"]
	candidateAttributes: list[NaturalLanguagePreviewCandidateView] = Field(default_factory=list)
	parsedCondition: NaturalLanguageParsedConditionView | None = None
	requiresStewardConfirmation: bool = True
	draftRulePreview: NaturalLanguageDraftRulePreviewView | None = None
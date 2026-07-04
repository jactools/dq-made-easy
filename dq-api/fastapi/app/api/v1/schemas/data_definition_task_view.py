from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import Field

from app.schemas.pydantic_base import SnakeModel


class DataDefinitionTaskContextDocumentView(SnakeModel):
    documentType: str = Field(min_length=1)
    name: str = Field(min_length=1)
    content: str = Field(min_length=1)
    sourceUri: str | None = None


class DataDefinitionTaskFeedbackItemView(SnakeModel):
    feedbackId: str | None = None
    sourceRole: str = Field(min_length=1)
    comment: str = Field(min_length=1)
    authorName: str | None = None
    disposition: str | None = None
    targetIds: list[str] = Field(default_factory=list)


class DataDefinitionTaskBoardApprovalView(SnakeModel):
    boardName: str | None = None
    status: str = "pending"
    approverName: str | None = None
    approvalNotes: str | None = None
    approvedAt: str | None = None


class DataDefinitionTaskCreateRequestView(SnakeModel):
    currentWorkspaceId: str = Field(min_length=1)
    versionId: str = Field(min_length=1)
    selectedAttributeIds: list[str] = Field(min_length=1)
    userInput: str | None = None
    policies: list[str] = Field(default_factory=list)
    contextDocuments: list[DataDefinitionTaskContextDocumentView] = Field(default_factory=list)
    feedbackItems: list[DataDefinitionTaskFeedbackItemView] = Field(default_factory=list)
    boardApproval: DataDefinitionTaskBoardApprovalView | None = None
    stewardName: str | None = None
    boardName: str = "Data Definition Board"
    glossaryName: str | None = None
    glossaryDisplayName: str | None = None
    domainName: str | None = None
    sourceSystem: str | None = None
    autoImport: bool = False


class DataDefinitionTaskApprovalUpdateRequestView(SnakeModel):
    boardApproval: DataDefinitionTaskBoardApprovalView
    autoImport: bool = False


class DataDefinitionTaskCreateResponseView(SnakeModel):
    success: bool = True
    queued: bool = True
    requestId: str
    eventsUrl: str
    message: str


class DataDefinitionTaskStatusView(SnakeModel):
    requestId: str
    currentWorkspaceId: str
    versionId: str | None = None
    selectedAttributeIds: list[str] = Field(default_factory=list)
    prompt: str
    requestedByUserId: str | None = None
    requestedByEmail: str | None = None
    requestedAt: str | None = None
    startedAt: str | None = None
    completedAt: str | None = None
    status: Literal["pending", "started", "completed", "failed"]
    errorMessage: str | None = None
    monitoringState: Literal["running", "stale", "terminal", "unavailable"] = Field(
        description="API-derived monitoring signal for whether the worker heartbeat is active, stale, terminal, or unavailable."
    )
    analysisType: str
    analysisProvider: str
    autoImport: bool = False
    taskPayload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None


class DataDefinitionTaskStatusResponseView(SnakeModel):
    success: bool = True
    request: DataDefinitionTaskStatusView


class DataDefinitionTaskHistoryResponseView(SnakeModel):
    success: bool = True
    requests: list[DataDefinitionTaskStatusView] = Field(default_factory=list)
    count: int = 0


class DataDefinitionTaskAuditEventView(SnakeModel):
    id: str
    requestId: str
    action: str
    fromStatus: str | None = None
    toStatus: str | None = None
    actorId: str | None = None
    changedAt: str
    details: dict[str, Any] = Field(default_factory=dict)


class DataDefinitionTaskAuditHistoryResponseView(SnakeModel):
    success: bool = True
    requestId: str
    events: list[DataDefinitionTaskAuditEventView] = Field(default_factory=list)
    count: int = 0


class DataDefinitionTaskImportResponseView(SnakeModel):
    success: bool = True
    requestId: str
    message: str
    importReport: dict[str, Any]
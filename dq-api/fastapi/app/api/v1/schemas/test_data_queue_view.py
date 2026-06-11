from typing import Any

from pydantic import ConfigDict, Field

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class TestDataAttributeRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    name: str
    type: str = "text"
    nullable: bool = True
    format: str = ""
    isPrimaryKey: bool = False


class CreateQueuedTestDataRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    targetType: str
    targetId: str
    sampleCount: int = Field(default=10, ge=1, le=1000)
    sourceName: str | None = None
    versionName: str | int | None = None
    dataObjectId: str | None = None
    attributes: list[TestDataAttributeRequest] = Field(default_factory=list)


class QueuedTestDataRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    requestId: str
    jobId: str
    businessKey: str | None = None
    status: str
    targetType: str
    targetId: str
    sampleCount: int
    requestedAt: str
    startedAt: str | None = None
    completedAt: str | None = None
    errorMessage: str | None = None
    correlationId: str | None = None
    eventsUrl: str | None = None
    result: dict[str, Any] | None = None
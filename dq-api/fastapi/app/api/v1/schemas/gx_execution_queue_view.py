from pydantic import ConfigDict, Field

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class GxExecutionQueueStatusView(SnakeModel):
    """Queue visibility for a queued GX execution run.

    The dispatch queue is a Redis list. The API enqueues via LPUSH.

    Many workers consume via (B)RPOP to process oldest-first.
    We report both:
    - index_from_head: 0 = newest element
    - index_from_tail: 0 = oldest element (next to be popped by RPOP)
    """

    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    runId: str = Field(exclude=True)
    businessKey: str | None = None
    correlationId: str | None = None
    queueKey: str
    queueMessageId: str = Field(exclude=True)

    queueLength: int = Field(ge=0)
    inspectedDepth: int = Field(ge=0)

    found: bool
    indexFromHead: int | None = Field(default=None, ge=0)
    indexFromTail: int | None = Field(default=None, ge=0)

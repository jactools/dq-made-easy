from __future__ import annotations

from fastapi import APIRouter

from app.schemas.pydantic_base import SnakeModel

router = APIRouter()


class DemoView(SnakeModel):
    camelCaseField: str
    anotherField: int


@router.get("/demo/snake", response_model=DemoView, tags=["demo"])
async def get_demo():
    """Return a demo payload where the external JSON keys are snake_case."""
    return DemoView(camelCaseField="value", anotherField=123)

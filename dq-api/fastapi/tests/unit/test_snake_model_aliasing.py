from app.schemas.pydantic_base import SnakeModel


class MyModel(SnakeModel):
    userId: str
    createdAt: int


def test_snake_aliasing_on_dump():
    m = MyModel(userId="u1", createdAt=123)
    out = m.model_dump(by_alias=True)
    assert "user_id" in out and out["user_id"] == "u1"
    assert "created_at" in out and out["created_at"] == 123

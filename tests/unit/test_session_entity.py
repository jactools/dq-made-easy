from __future__ import annotations
from datetime import datetime

from app.domain.entities.session import SessionEntity


def test_session_entity_fields_and_defaults():
    now = datetime.utcnow()
    s = SessionEntity(id="sess-1", user_id="user-1", last_activity=now)
    assert s.id == "sess-1"
    assert s.user_id == "user-1"
    assert s.last_activity == now


def test_session_entity_mapping_and_accessors():
    now = datetime.utcnow()
    s = SessionEntity(id="sess-2", user_id="user-1", last_activity=now)

    # attribute access
    assert s.id == "sess-2"
    assert s.user_id == "user-1"

    # iteration / serialization helpers via model_dump
    items = s.model_dump()
    assert items["id"] == "sess-2"
    assert "user_id" in items.keys()
    assert "user-1" in items.values()


def test_session_entity_equality_with_dict():
    now = datetime.utcnow()
    s = SessionEntity(id="sess-3", user_id="user-3", last_activity=now)
    dumped = s.model_dump()
    assert dumped["id"] == "sess-3"
    assert dumped["user_id"] == "user-3"
    assert not (dumped == {"id": "other"})

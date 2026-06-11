import pytest

from app.core.request_context import (
    clear_auth_context,
    get_consumer_groups,
    get_correlation_id,
    get_scopes,
    get_user_id,
    set_consumer_groups,
    set_correlation_id,
    set_scopes,
    set_user_id,
)

pytestmark = pytest.mark.usefixtures("clone_payload")


def test_request_auth_context_round_trip() -> None:
    set_user_id("user-123")
    set_scopes(["dq:rules:read", "dq:rules:view"])

    assert get_user_id() == "user-123"
    assert get_scopes() == ("dq:rules:read", "dq:rules:view")

    clear_auth_context()

    assert get_user_id() is None
    assert get_scopes() == ()


def test_request_correlation_context_round_trip() -> None:
    set_correlation_id("cid-ctx-123")
    assert get_correlation_id() == "cid-ctx-123"

    set_correlation_id(None)
    assert get_correlation_id() is None


def test_request_consumer_groups_context_round_trip() -> None:
    set_consumer_groups(["group-a", "group-b"])

    assert get_consumer_groups() == ("group-a", "group-b")

    clear_auth_context()

    assert get_consumer_groups() == ()


def test_set_scopes_and_consumer_groups_accept_tuple_input() -> None:
    set_scopes(("scope.read", "scope.write"))
    set_consumer_groups(("consumers",))

    assert get_scopes() == ("scope.read", "scope.write")
    assert get_consumer_groups() == ("consumers",)
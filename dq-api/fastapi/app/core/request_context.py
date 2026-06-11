from contextvars import ContextVar

_correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)
_scopes_ctx: ContextVar[tuple[str, ...]] = ContextVar("scopes", default=())
_consumer_groups_ctx: ContextVar[tuple[str, ...]] = ContextVar("consumer_groups", default=())


def set_correlation_id(correlation_id: str | None) -> None:
    _correlation_id_ctx.set(correlation_id)


def get_correlation_id() -> str | None:
    return _correlation_id_ctx.get()


def set_user_id(user_id: str | None) -> None:
    _user_id_ctx.set(user_id)


def get_user_id() -> str | None:
    return _user_id_ctx.get()


def set_scopes(scopes: list[str] | tuple[str, ...]) -> None:
    _scopes_ctx.set(tuple(scopes))


def get_scopes() -> tuple[str, ...]:
    return _scopes_ctx.get()


def set_consumer_groups(groups: list[str] | tuple[str, ...]) -> None:
    _consumer_groups_ctx.set(tuple(groups))


def get_consumer_groups() -> tuple[str, ...]:
    return _consumer_groups_ctx.get()


def clear_auth_context() -> None:
    set_user_id(None)
    set_scopes(())
    set_consumer_groups(())

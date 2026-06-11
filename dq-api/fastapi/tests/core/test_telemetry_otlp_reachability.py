from __future__ import annotations

from app.core import telemetry


class _DummyConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_otlp_endpoint_reachable_when_socket_connects(monkeypatch) -> None:
    monkeypatch.setattr(
        telemetry.socket,
        "create_connection",
        lambda target, timeout: _DummyConnection(),
    )

    assert telemetry._is_otlp_endpoint_reachable("http://localhost:4317") is True


def test_otlp_endpoint_unreachable_when_socket_fails(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise OSError("connection failed")

    monkeypatch.setattr(telemetry.socket, "create_connection", _raise)

    assert telemetry._is_otlp_endpoint_reachable("http://localhost:4317") is False


def test_otlp_target_defaults_port_for_host_only_endpoint() -> None:
    assert telemetry._otlp_target("localhost:4317") == ("localhost", 4317)

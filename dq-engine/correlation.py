from __future__ import annotations

from collections.abc import Mapping

CORRELATION_HEADER = "X-Correlation-ID"


def extract_correlation_id(headers: Mapping[str, str] | None) -> str | None:
    """Return a normalized correlation id from inbound headers if present."""
    if not headers:
        return None
    raw = headers.get(CORRELATION_HEADER) or headers.get(CORRELATION_HEADER.lower())
    value = str(raw or "").strip()
    return value or None


def build_forward_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    """Build outbound headers that preserve correlation context across services."""
    correlation_id = extract_correlation_id(headers)
    if correlation_id is None:
        return {}
    return {CORRELATION_HEADER: correlation_id}

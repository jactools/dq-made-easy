from __future__ import annotations

import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from correlation import CORRELATION_HEADER
from correlation import build_forward_headers


def _worker_correlation_id_from_payload(payload: dict[str, object]) -> str:
    """Mirror the worker-side normalization contract for correlation ids."""
    value = str(payload.get("correlation_id") or "").strip()
    return value or "n/a"


class CorrelationRuntimeChainTests(unittest.TestCase):
    def test_single_correlation_id_survives_api_engine_worker_chain(self) -> None:
        # Simulated API ingress header.
        api_headers = {CORRELATION_HEADER: "cid-chain-001"}

        # Engine outbound forwarding.
        forwarded = build_forward_headers(api_headers)
        self.assertEqual(forwarded.get(CORRELATION_HEADER), "cid-chain-001")

        # Simulated worker queue handoff payload.
        worker_payload: dict[str, object] = {
            "profiling_request_id": "req-1",
            "data_source_id": "ds-1",
            "user_id": "u-1",
            "data_source_name": "source-1",
            "source_type": "azure-sql",
            "correlation_id": forwarded.get(CORRELATION_HEADER),
        }

        worker_cid = _worker_correlation_id_from_payload(worker_payload)
        self.assertEqual(worker_cid, "cid-chain-001")


if __name__ == "__main__":
    unittest.main()
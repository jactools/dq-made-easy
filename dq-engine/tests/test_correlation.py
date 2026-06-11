from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from correlation import CORRELATION_HEADER
from correlation import build_forward_headers
from correlation import extract_correlation_id


class CorrelationHelpersTests(unittest.TestCase):
    def test_extract_correlation_id_from_canonical_header(self) -> None:
        value = extract_correlation_id({CORRELATION_HEADER: "cid-123"})
        self.assertEqual(value, "cid-123")

    def test_extract_correlation_id_from_lowercase_header(self) -> None:
        value = extract_correlation_id({"x-correlation-id": "cid-lower"})
        self.assertEqual(value, "cid-lower")

    def test_build_forward_headers_empty_when_missing(self) -> None:
        self.assertEqual(build_forward_headers({}), {})

    def test_build_forward_headers_contains_correlation(self) -> None:
        headers = build_forward_headers({"x-correlation-id": "cid-propagate"})
        self.assertEqual(headers, {CORRELATION_HEADER: "cid-propagate"})


if __name__ == "__main__":
    unittest.main()

import os
import sys
import json
import logging


# Ensure local package source is importable when running this test file directly.
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(ROOT_DIR, "dq-utils", "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import importlib.util

# Load the module directly from its source file path to avoid importing
# dq_utils.__init__ (which pulls heavy optional deps during import).
mod_path = os.path.join(SRC_DIR, "dq_utils", "logging_utils.py")
spec = importlib.util.spec_from_file_location("dq_utils_logging_utils", mod_path)
logging_utils = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(logging_utils)

_JsonFormatter = logging_utils._JsonFormatter
configure_logging = logging_utils.configure_logging
log_event = logging_utils.log_event


def test_json_formatter_includes_custom_fields():
    fmt = _JsonFormatter()
    record = logging.LogRecord(
        name="mylogger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello",
        args=(),
        exc_info=None,
    )
    # add a non-standard attribute which should be included in the JSON
    record.__dict__["custom_key"] = "custom_value"

    payload = fmt.format(record)
    data = json.loads(payload)

    assert data["logger"] == "mylogger"
    assert data["msg"] == "hello"
    assert data["custom_key"] == "custom_value"
    assert "ts" in data and "level" in data


def test_configure_logging_sets_handler_and_level():
    # configure logging and assert root logger has a StreamHandler and correct level
    configure_logging("WARNING")
    root = logging.getLogger()
    assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    assert root.level == logging.WARNING


def test_log_event_safe_extra_and_reserved_prefix():
    captured = []

    class ListHandler(logging.Handler):
        def emit(self, rec: logging.LogRecord) -> None:  # type: ignore[override]
            # store a shallow copy of the record dict so assertions can inspect it
            captured.append(rec.__dict__.copy())

    logger = logging.getLogger("test_logger_for_log_event")
    # ensure a clean handler set for the logger used in this test
    logger.handlers.clear()
    handler = ListHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    # Call log_event with a reserved key ('message') and a normal key ('user')
    log_event(logger, "evt", level="info", message="danger", user="alice")

    assert captured, "expected a log record to be emitted"
    rec = captured[-1]

    # reserved key should be prefixed to avoid overwriting LogRecord internals
    assert rec.get("ctx_message") == "danger"
    assert rec.get("user") == "alice"
    assert rec.get("msg") == "evt"

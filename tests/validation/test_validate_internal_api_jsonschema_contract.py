from __future__ import annotations

import builtins
import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validation" / "validate_internal_api_jsonschema_contract.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_internal_api_jsonschema_contract", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_load_live_openapi_propagates_import_failure(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module, "_prepare_fastapi_contract_env", lambda: None)

    real_import = builtins.__import__

    def broken_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "app.main":
            raise ImportError("simulated app import failure")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", broken_import)

    with pytest.raises(ImportError, match="simulated app import failure"):
        module._load_live_openapi()

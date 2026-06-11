import json
import os
from types import SimpleNamespace

import pytest

from app.application.services import version_catalog as vc


def _set_module_file(monkeypatch, tmp_path, depth=3):
    # Point module __file__ into a temp directory so parent traversal is deterministic
    target = tmp_path / "a" / "b" / "c" / "module.py"
    target.parent.mkdir(parents=True)
    monkeypatch.setattr(vc, "__file__", str(target))
    return target


def test_read_version_from_package_json_and_api_version(monkeypatch, tmp_path):
    target = _set_module_file(monkeypatch, tmp_path)

    # create package.json in an ancestor
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({"version": "1.2.3"}), encoding="utf-8")

    # ensure the candidate search sees our package.json
    assert vc._read_api_version() == "1.2.3"

    # malformed package.json yields None and falls back to unknown
    pkg.write_text("not-a-json", encoding="utf-8")
    assert vc._read_version_from_package_json(pkg) is None


def test_read_version_manifest_valid_and_malformed(monkeypatch, tmp_path):
    _set_module_file(monkeypatch, tmp_path)

    manifest = tmp_path / "VERSION_MANIFEST.json"
    manifest.write_text(json.dumps({"apps": {"api": "5.5.5", "ui": "6.6.6"}, "components": {"c1": "v1"}}), encoding="utf-8")

    m = vc._read_version_manifest()
    assert m["apps"]["api"] == "5.5.5"
    assert m["apps"]["ui"] == "6.6.6"
    assert m["components"]["c1"] == "v1"

    # malformed JSON should be skipped and result in empty maps
    manifest.write_text("[not,a,dict]", encoding="utf-8")
    m2 = vc._read_version_manifest()
    # with malformed manifest we expect empty fallback
    assert isinstance(m2, dict)
    assert m2["apps"] == {}


def test_resolve_api_version_priority(monkeypatch, tmp_path):
    # Test manifest priority over env
    _set_module_file(monkeypatch, tmp_path)
    manifest = tmp_path / "VERSION_MANIFEST.json"
    manifest.write_text(json.dumps({"apps": {"api": "9.9.9"}}), encoding="utf-8")

    # ensure env doesn't override manifest
    monkeypatch.setenv("API_VERSION", "2.2.2")
    assert vc.resolve_api_version(None) == "9.9.9"

    # remove manifest and test env fallback
    manifest.unlink()
    monkeypatch.setenv("API_VERSION", "2.2.2")
    assert vc.resolve_api_version(None) == "2.2.2"


def test_resolve_ui_version_env_and_manifest(monkeypatch, tmp_path):
    _set_module_file(monkeypatch, tmp_path)
    manifest = tmp_path / "VERSION_MANIFEST.json"
    manifest.write_text(json.dumps({"apps": {"ui": "7.7.7"}}), encoding="utf-8")

    assert vc.resolve_ui_version() == "7.7.7"

    manifest.unlink()
    monkeypatch.setenv("UI_VERSION", "3.3.3")
    assert vc.resolve_ui_version() == "3.3.3"


def test_normalize_component_map():
    raw = {" comp ": " v1 ", "": "x", "ok": ""}
    normalized = vc._normalize_component_map(raw)
    assert normalized == {"comp": "v1"}


def test_build_version_catalog_no_repo():
    # If no repository provided, returns unknowns
    catalog = vc.build_version_catalog(None, None)
    assert catalog["apps"]["api"] == "unknown"
    assert catalog["apps"]["ui"] == "unknown"


def test_build_version_catalog_from_repo():
    class FakeConfig:
        versionCatalogApi = "a.v"
        versionCatalogUi = "u.v"
        versionCatalogComponents = {"x": "1"}

    class Repo:
        def get_app_config(self):
            return FakeConfig()

    catalog = vc.build_version_catalog(None, Repo())
    assert catalog["apps"]["api"] == "a.v"
    assert catalog["apps"]["ui"] == "u.v"
    assert catalog["components"]["x"] == "1"

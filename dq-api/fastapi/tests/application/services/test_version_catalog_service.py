import json
from pathlib import Path
from types import SimpleNamespace

import app.application.services.version_catalog as version_catalog_mod
from app.application.services.version_catalog import _candidate_package_json_paths
from app.application.services.version_catalog import _normalize_component_map
from app.application.services.version_catalog import _read_api_version
from app.application.services.version_catalog import _read_version_from_package_json
from app.application.services.version_catalog import _read_version_manifest
from app.application.services.version_catalog import build_version_catalog
from app.application.services.version_catalog import resolve_api_version
from app.application.services.version_catalog import resolve_ui_version


def test_candidate_package_json_paths_handles_shallow_source_path() -> None:
    source_file = Path("/app/application/services/version_catalog.py")

    candidates = _candidate_package_json_paths(source_file)

    assert candidates
    assert all(path.name == "package.json" for path in candidates)
    assert len(candidates) == len(set(candidates))


class _StubAppConfigRepository:
    def __init__(self, config: SimpleNamespace) -> None:
        self._config = config
        self.set_calls: list[dict[str, object]] = []

    def get_app_config(self) -> SimpleNamespace:
        return self._config

    def set_app_config(self, payload: dict[str, object]) -> SimpleNamespace:
        self.set_calls.append(payload)
        for key, value in payload.items():
            setattr(self._config, key, value)
        return self._config


def test_build_version_catalog_prefers_db_values(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.application.services.version_catalog._read_version_manifest",
        lambda: {
            "apps": {"api": "1.0.0", "ui": "1.0.0"},
            "components": {"kong": "3.9.0"},
        },
    )

    repository = _StubAppConfigRepository(
        SimpleNamespace(
            versionCatalogApi="2.0.0",
            versionCatalogUi="2.1.0",
            versionCatalogComponents={"kong": "4.0.0"},
        )
    )

    catalog = build_version_catalog(request=None, app_config_repository=repository)

    assert catalog["apps"] == {"api": "2.0.0", "ui": "2.1.0"}
    assert catalog["components"] == {"kong": "4.0.0"}
    assert repository.set_calls == []


def test_build_version_catalog_hydrates_db_when_missing(monkeypatch) -> None:
    repository = _StubAppConfigRepository(
        SimpleNamespace(
            versionCatalogApi="unknown",
            versionCatalogUi="unknown",
            versionCatalogComponents={},
        )
    )

    catalog = build_version_catalog(request=None, app_config_repository=repository)

    assert catalog["apps"] == {"api": "unknown", "ui": "unknown"}
    assert catalog["components"] == {}
    assert repository.set_calls == []


def test_build_version_catalog_falls_back_ui_to_api_when_ui_unknown(monkeypatch) -> None:
    del monkeypatch

    repository = _StubAppConfigRepository(
        SimpleNamespace(
            versionCatalogApi="0.6.2",
            versionCatalogUi="unknown",
            versionCatalogComponents={},
        )
    )

    catalog = build_version_catalog(request=None, app_config_repository=repository)

    assert catalog["apps"] == {"api": "0.6.2", "ui": "unknown"}
    assert repository.set_calls == []


def test_read_version_helpers_from_temp_tree(tmp_path, monkeypatch) -> None:
    services_dir = tmp_path / "dq-api" / "fastapi" / "app" / "application" / "services"
    services_dir.mkdir(parents=True)
    fake_source = services_dir / "version_catalog.py"
    fake_source.write_text("# fake source\n", encoding="utf-8")

    package_json = tmp_path / "dq-api" / "package.json"
    package_json.write_text(json.dumps({"version": "9.8.7"}), encoding="utf-8")

    manifest = tmp_path / "dq-api" / "VERSION_MANIFEST.json"
    manifest.write_text(
        json.dumps({"apps": {"api": "7.0.0", "ui": "7.1.0"}, "components": {"kong": "3.9.0"}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(version_catalog_mod, "__file__", str(fake_source))

    assert _read_api_version() == "9.8.7"
    assert _read_version_manifest() == {
        "apps": {"api": "7.0.0", "ui": "7.1.0"},
        "components": {"kong": "3.9.0"},
    }


def test_read_version_from_package_json_handles_invalid_cases(tmp_path) -> None:
    blank_version = tmp_path / "blank-package.json"
    blank_version.write_text(json.dumps({"version": "   "}), encoding="utf-8")

    invalid_json = tmp_path / "invalid-package.json"
    invalid_json.write_text("{oops", encoding="utf-8")

    assert _read_version_from_package_json(blank_version) is None
    assert _read_version_from_package_json(invalid_json) is None


def test_read_version_manifest_skips_invalid_payloads_until_valid_manifest(tmp_path, monkeypatch) -> None:
    services_dir = tmp_path / "dq-api" / "fastapi" / "app" / "application" / "services"
    services_dir.mkdir(parents=True)
    fake_source = services_dir / "version_catalog.py"
    fake_source.write_text("# fake source\n", encoding="utf-8")

    invalid_manifest = tmp_path / "dq-api" / "fastapi" / "VERSION_MANIFEST.json"
    invalid_manifest.write_text("[]", encoding="utf-8")

    valid_manifest = tmp_path / "dq-api" / "version-manifest.json"
    valid_manifest.write_text(json.dumps({"apps": [], "components": {"api": "1.2.3"}}), encoding="utf-8")

    monkeypatch.setattr(version_catalog_mod, "__file__", str(fake_source))

    assert _read_version_manifest() == {"apps": {}, "components": {"api": "1.2.3"}}


def test_read_version_manifest_returns_empty_when_only_invalid_manifests_exist(tmp_path, monkeypatch) -> None:
    services_dir = tmp_path / "dq-api" / "fastapi" / "app" / "application" / "services"
    services_dir.mkdir(parents=True)
    fake_source = services_dir / "version_catalog.py"
    fake_source.write_text("# fake source\n", encoding="utf-8")

    invalid_manifest = tmp_path / "dq-api" / "VERSION_MANIFEST.json"
    invalid_manifest.write_text("{not-json", encoding="utf-8")

    monkeypatch.setattr(version_catalog_mod, "__file__", str(fake_source))

    assert _read_version_manifest() == {"apps": {}, "components": {}}


def test_read_api_version_returns_unknown_when_no_package_versions_resolve(tmp_path, monkeypatch) -> None:
    services_dir = tmp_path / "dq-api" / "fastapi" / "app" / "application" / "services"
    services_dir.mkdir(parents=True)
    fake_source = services_dir / "version_catalog.py"
    fake_source.write_text("# fake source\n", encoding="utf-8")

    missing_version_package = tmp_path / "dq-api" / "package.json"
    missing_version_package.write_text(json.dumps({"name": "dq-api"}), encoding="utf-8")

    monkeypatch.setattr(version_catalog_mod, "__file__", str(fake_source))

    assert _read_api_version() == "unknown"


def test_resolve_api_version_prefers_manifest_and_package_before_request(monkeypatch) -> None:
    request = SimpleNamespace(
        app=SimpleNamespace(
            version="8.8.8",
            openapi=lambda: {"info": {"version": "7.7.7"}},
        )
    )

    monkeypatch.setattr(version_catalog_mod, "_read_version_manifest", lambda: {"apps": {"api": "9.9.9"}, "components": {}})
    monkeypatch.setattr(version_catalog_mod, "_read_api_version", lambda: "6.6.6")

    assert resolve_api_version(request) == "9.9.9"

    monkeypatch.setattr(version_catalog_mod, "_read_version_manifest", lambda: {"apps": {}, "components": {}})
    assert resolve_api_version(request) == "6.6.6"


def test_resolve_api_version_uses_request_app_version_before_openapi(monkeypatch) -> None:
    request = SimpleNamespace(
        app=SimpleNamespace(
            version="8.8.8",
            openapi=lambda: {"info": {"version": "7.7.7"}},
        )
    )

    monkeypatch.setattr(version_catalog_mod, "_read_version_manifest", lambda: {"apps": {}, "components": {}})
    monkeypatch.setattr(version_catalog_mod, "_read_api_version", lambda: "unknown")
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("API_VERSION", raising=False)
    monkeypatch.delenv("SERVICE_VERSION", raising=False)
    monkeypatch.delenv("OTEL_SERVICE_VERSION", raising=False)

    assert resolve_api_version(request) == "8.8.8"


def test_resolve_api_version_fallback_order(monkeypatch) -> None:
    request = SimpleNamespace(
        app=SimpleNamespace(
            version=" ",
            openapi=lambda: {"info": {"version": "5.4.3"}},
        )
    )

    monkeypatch.setattr(version_catalog_mod, "_read_version_manifest", lambda: {"apps": {}, "components": {}})
    monkeypatch.setattr(version_catalog_mod, "_read_api_version", lambda: "unknown")
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("UI_VERSION", raising=False)
    monkeypatch.setenv("API_VERSION", "4.3.2")

    assert resolve_api_version(request) == "5.4.3"

    request_env = SimpleNamespace(
        app=SimpleNamespace(
            version="unknown",
            openapi=lambda: {"info": {"version": "unknown"}},
        )
    )
    monkeypatch.setenv("APP_VERSION", "6.5.4")
    assert resolve_api_version(request_env) == "6.5.4"


def test_resolve_api_version_uses_env_sequence_and_unknown_fallback(monkeypatch) -> None:
    request = SimpleNamespace(
        app=SimpleNamespace(
            version="unknown",
            openapi=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )
    )

    monkeypatch.setattr(version_catalog_mod, "_read_version_manifest", lambda: {"apps": {}, "components": {}})
    monkeypatch.setattr(version_catalog_mod, "_read_api_version", lambda: "unknown")
    monkeypatch.setenv("APP_VERSION", "   ")
    monkeypatch.setenv("API_VERSION", "unknown")
    monkeypatch.setenv("SERVICE_VERSION", "4.4.4")
    monkeypatch.delenv("OTEL_SERVICE_VERSION", raising=False)

    assert resolve_api_version(request) == "4.4.4"

    monkeypatch.delenv("SERVICE_VERSION", raising=False)
    assert resolve_api_version(None) == "unknown"


def test_resolve_ui_version_and_normalize_component_map(monkeypatch) -> None:
    monkeypatch.setattr(version_catalog_mod, "_read_version_manifest", lambda: {"apps": {}, "components": {}})
    monkeypatch.setenv("UI_VERSION", "2.4.6")

    assert resolve_ui_version() == "2.4.6"
    assert _normalize_component_map({" api ": " 1.0.0 ", "": "skip", "ui": "   "}) == {"api": "1.0.0"}
    assert _normalize_component_map(None) == {}


def test_resolve_ui_version_prefers_manifest_then_unknown(monkeypatch) -> None:
    monkeypatch.setattr(version_catalog_mod, "_read_version_manifest", lambda: {"apps": {"ui": "3.3.3"}, "components": {}})
    monkeypatch.setenv("UI_VERSION", "2.2.2")

    assert resolve_ui_version() == "3.3.3"

    monkeypatch.setattr(version_catalog_mod, "_read_version_manifest", lambda: {"apps": {}, "components": {}})
    monkeypatch.setenv("UI_VERSION", "   ")

    assert resolve_ui_version() == "unknown"


def test_build_version_catalog_handles_missing_repository_and_repository_errors() -> None:
    missing_repo_catalog = build_version_catalog(request=None, app_config_repository=None)

    class _FailingRepository:
        def get_app_config(self):
            raise RuntimeError("db unavailable")

    failing_repo_catalog = build_version_catalog(request=None, app_config_repository=_FailingRepository())

    assert missing_repo_catalog == {"apps": {"ui": "unknown", "api": "unknown"}, "components": {}}
    assert failing_repo_catalog == {"apps": {"ui": "unknown", "api": "unknown"}, "components": {}}


def test_build_version_catalog_normalizes_component_values_from_repository() -> None:
    repository = _StubAppConfigRepository(
        SimpleNamespace(
            versionCatalogApi=" 1.2.3 ",
            versionCatalogUi="",
            versionCatalogComponents={" api ": " 2.0.0 ", "blank": "   "},
        )
    )

    catalog = build_version_catalog(request=None, app_config_repository=repository)

    assert catalog == {
        "apps": {"api": "1.2.3", "ui": "unknown"},
        "components": {"api": "2.0.0"},
    }

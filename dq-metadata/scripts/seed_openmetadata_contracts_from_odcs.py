#!/usr/bin/env python3
"""Seed repository ODCS 3.1+ contracts into OpenMetadata."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import ssl
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request

import yaml

from openmetadata_tls import build_ssl_context


SSL_CONTEXT: ssl.SSLContext | None = None
UUID_NAMESPACE = uuid.UUID("e0baf84a-5b57-4c5d-9db6-279972baa2de")
SUPPORTED_EXTENSIONS = (".odcs.yaml", ".odcs.yml")
DEFAULT_STRING_LENGTHS = {
    "uuid": 36,
    "char": 1,
    "string": 255,
    "varchar": 255,
    "text": 65535,
}


class OpenMetadataRequestError(RuntimeError):
    def __init__(self, method: str, url: str, status_code: int, body: str) -> None:
        super().__init__(f"OpenMetadata request failed: {method} {url} -> HTTP {status_code}: {body}")
        self.method = method
        self.url = url
        self.status_code = status_code
        self.body = body


@dataclass(frozen=True)
class EntityTarget:
    service_name: str
    service_type: str
    host_port: str
    database_name: str
    schema_name: str
    table_name: str

    @property
    def database_fqn(self) -> str:
        return f"{self.service_name}.{self.database_name}"

    @property
    def schema_fqn(self) -> str:
        return f"{self.database_fqn}.{self.schema_name}"

    @property
    def table_fqn(self) -> str:
        return f"{self.schema_fqn}.{self.table_name}"


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def normalize_endpoint(endpoint: str) -> str:
    base = endpoint.rstrip("/")
    if base.endswith("/api"):
        return base
    return f"{base}/api"


def default_login_email() -> str:
    return clean(os.environ.get("OM_EMAIL") or os.environ.get("OPENMETADATA_OIDC_SEED_USERNAME"))


def default_login_password() -> str:
    return clean(
        os.environ.get("OM_PASSWORD")
        or os.environ.get("OPENMETADATA_OIDC_SEED_PASSWORD")
        or os.environ.get("KEYCLOAK_SEEDED_USER_PASSWORD")
        or os.environ.get("KEYCLOAK_USER_PASSWORD")
    )


def slugify(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()
    if not normalized:
        normalized = fallback
    if normalized[0].isdigit():
        normalized = f"n_{normalized}"
    return normalized[:64]


def stable_uuid(value: str) -> str:
    seed = clean(value) or "missing"
    return str(uuid.uuid5(UUID_NAMESPACE, seed))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).resolve().parents[2]
    parser.add_argument(
        "--contracts-dir",
        default=str(repo_root / "data_sources" / "contracts"),
        help="Directory containing .odcs.yaml/.odcs.yml files",
    )
    parser.add_argument(
        "--output-dir",
        default=str(repo_root / "tmp" / "openmetadata-odcs"),
        help="Directory where OpenMetadata import payloads are written",
    )
    parser.add_argument(
        "--endpoint",
        default="https://openmetadata.jac.dot:8585/api",
        help="OpenMetadata API base URL",
    )
    parser.add_argument("--token", default="", help="Bearer token for OpenMetadata")
    parser.add_argument("--email", default=default_login_email(), help="OpenMetadata login email")
    parser.add_argument("--password", default=default_login_password(), help="OpenMetadata login password")
    parser.add_argument(
        "--password-b64",
        default="",
        help="Base64-encoded OpenMetadata password for login endpoint",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue seeding remaining contracts after a contract-level failure",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write transformed contracts without calling OpenMetadata",
    )
    return parser.parse_args()


def request_json(
    api_base: str,
    path: str,
    *,
    method: str = "GET",
    token: str = "",
    body: Any | None = None,
    raw_body: bytes | str | None = None,
    params: dict[str, Any] | None = None,
    content_type: str = "application/json",
    allow_not_found: bool = False,
) -> dict[str, Any] | None:
    query = f"?{parse.urlencode(params, doseq=True)}" if params else ""
    url = f"{api_base}{path}{query}"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if body is not None and raw_body is not None:
        raise ValueError("request_json accepts either body or raw_body, not both")
    if body is not None:
        headers["Content-Type"] = content_type
        data = json.dumps(body).encode("utf-8")
    elif raw_body is not None:
        headers["Content-Type"] = content_type
        data = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body

    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=30, context=SSL_CONTEXT) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        if allow_not_found and exc.code == 404:
            return None
        raise OpenMetadataRequestError(method, url, exc.code, body_text) from exc

    if not raw:
        return {}
    return json.loads(raw)


def login(api_base: str, email: str, password: str, password_b64: str) -> str:
    encoded_password = password_b64 or base64.b64encode(password.encode("utf-8")).decode("ascii")
    payload = {"email": email, "password": encoded_password}
    failures: list[str] = []

    for path in ("/v1/users/login", "/v1/auth/login"):
        try:
            response = request_json(api_base, path, method="POST", body=payload)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{path}: {exc}")
            continue

        token = clean((response or {}).get("accessToken"))
        if token:
            return token
        failures.append(f"{path}: response did not include accessToken")

    raise RuntimeError("Failed OpenMetadata login. " + " | ".join(failures))


def discover_contract_files(contracts_dir: Path) -> list[Path]:
    if not contracts_dir.is_dir():
        raise RuntimeError(f"Contracts directory does not exist: {contracts_dir}")
    files = [
        path
        for path in sorted(contracts_dir.rglob("*"))
        if path.is_file() and any(path.name.endswith(ext) for ext in SUPPORTED_EXTENSIONS)
    ]
    if not files:
        raise RuntimeError(f"No ODCS files found in {contracts_dir}")
    return files


def load_yaml_file(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"ODCS file must contain a YAML mapping: {path}")
    return payload


def parse_contract_version(raw_version: str) -> tuple[int, int, int]:
    normalized = clean(raw_version).lower()
    if normalized.startswith("v"):
        normalized = normalized[1:]
    match = re.fullmatch(r"(?P<major>\d+)(?:\.(?P<minor>\d+))?(?:\.(?P<patch>\d+))?", normalized)
    if not match:
        raise RuntimeError(f"Unsupported ODCS apiVersion: {raw_version!r}")
    return (
        int(match.group("major") or 0),
        int(match.group("minor") or 0),
        int(match.group("patch") or 0),
    )


def require_supported_contract(path: Path, contract: dict[str, Any]) -> None:
    api_version = clean(contract.get("apiVersion"))
    if not api_version:
        raise RuntimeError(
            f"ODCS contract must define apiVersion >= v3.1.0; legacy dataContractSpecification is not supported: {path}"
        )
    if parse_contract_version(api_version) < (3, 1, 0):
        raise RuntimeError(f"ODCS contract apiVersion must be >= v3.1.0: {path}")
    if clean(contract.get("kind")).lower() != "datacontract":
        raise RuntimeError(f"ODCS contract kind must be DataContract: {path}")
    if not isinstance(contract.get("servers"), dict) or not contract.get("servers"):
        raise RuntimeError(f"ODCS contract must define at least one server entry: {path}")
    schema = contract.get("schema")
    if not isinstance(schema, list) or not schema:
        raise RuntimeError(f"ODCS contract must define a non-empty schema array: {path}")


def select_server(contract: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    servers = contract.get("servers")
    if not isinstance(servers, dict) or not servers:
        raise RuntimeError("ODCS contract must define at least one server entry")
    for preferred in ("production", "prod"):
        value = servers.get(preferred)
        if isinstance(value, dict):
            return preferred, value
    for name, value in servers.items():
        if isinstance(value, dict):
            return clean(name) or "default", value
    raise RuntimeError("ODCS contract servers section does not contain an object-valued entry")


def map_service_type(raw_type: str) -> str:
    mapping = {
        "azure-sql": "AzureSQL",
        "azuresql": "AzureSQL",
        "mssql": "Mssql",
        "sqlserver": "Mssql",
        "postgres": "Postgres",
        "postgresql": "Postgres",
        "mysql": "Mysql",
    }
    normalized = clean(raw_type).lower()
    return mapping.get(normalized, "CustomDatabase")


def build_entity_target(path: Path, contract: dict[str, Any]) -> EntityTarget:
    server_name, server = select_server(contract)
    raw_type = clean(server.get("type"))
    service_type = map_service_type(raw_type)

    host = clean(server.get("server"))
    if not host:
        raise RuntimeError(f"Contract server definition is missing 'server': {path}")

    database_name = slugify(clean(server.get("database")), "default_db")
    schema_name = slugify(clean(server.get("schema")), "public")
    table_name = slugify(clean(server.get("table")), slugify(path.stem.replace(".odcs", ""), "contract_table"))

    host_port = host if ":" in host else f"{host}:1433"
    service_seed = f"{raw_type or service_type}_{host}_{server_name}"
    service_name = slugify(service_seed, "odcs_contract_service")

    return EntityTarget(
        service_name=service_name,
        service_type=service_type,
        host_port=host_port,
        database_name=database_name,
        schema_name=schema_name,
        table_name=table_name,
    )


def default_column_length(field_payload: dict[str, Any], options: dict[str, Any]) -> int | None:
    explicit_length = options.get("maxLength")
    if explicit_length is not None:
        return int(explicit_length)

    physical_type = clean(field_payload.get("physicalType")).lower()
    default_length = DEFAULT_STRING_LENGTHS.get(physical_type)
    if default_length is not None:
        return default_length

    logical_type = clean(field_payload.get("logicalType")).lower()
    if logical_type == "string":
        return DEFAULT_STRING_LENGTHS["string"]

    return None


def derive_contract_name(path: Path, contract: dict[str, Any], original_id: str) -> str:
    name = clean(contract.get("name"))
    if name:
        return slugify(name, "odcs_contract")
    if original_id:
        return slugify(original_id.split(":")[-1], "odcs_contract")
    return slugify(path.stem.replace(".odcs", ""), "odcs_contract")


def parse_duration(value: str, *, field_name: str) -> tuple[int, str]:
    raw = clean(value).lower()
    match = re.fullmatch(r"(?P<amount>\d+)(?:\s*)(?P<unit>[a-z]+)", raw)
    if not match:
        raise RuntimeError(f"Unsupported duration for {field_name}: {value!r}")

    amount = int(match.group("amount"))
    unit = match.group("unit")
    mapping = {
        "m": "minute",
        "min": "minute",
        "mins": "minute",
        "minute": "minute",
        "minutes": "minute",
        "h": "hour",
        "hr": "hour",
        "hrs": "hour",
        "hour": "hour",
        "hours": "hour",
        "d": "day",
        "day": "day",
        "days": "day",
    }
    normalized = mapping.get(unit)
    if normalized is None:
        raise RuntimeError(f"Unsupported duration unit for {field_name}: {value!r}")
    return amount, normalized


def select_schema_object(path: Path, contract: dict[str, Any], target: EntityTarget) -> dict[str, Any]:
    schema = contract.get("schema")
    if not isinstance(schema, list) or not schema:
        raise RuntimeError(f"ODCS contract must define a non-empty schema array: {path}")

    server = select_server(contract)[1]
    preferred_names = [clean(server.get("table")), target.table_name]
    for preferred_name in preferred_names:
        if not preferred_name:
            continue
        for item in schema:
            if isinstance(item, dict) and clean(item.get("name")) == preferred_name:
                return item

    for item in schema:
        if isinstance(item, dict):
            return item
    raise RuntimeError(f"ODCS contract schema does not contain an object-valued entry: {path}")


def normalize_description(payload: Any) -> str | dict[str, Any] | None:
    if isinstance(payload, str):
        value = clean(payload)
        return value or None
    if isinstance(payload, dict):
        sanitized = {
            key: value
            for key, value in payload.items()
            if (isinstance(value, str) and clean(value)) or (not isinstance(value, str) and value is not None)
        }
        return sanitized or None
    return None


def extract_max_latency(path: Path, contract: dict[str, Any]) -> dict[str, Any] | None:
    sla_properties = contract.get("slaProperties")
    if isinstance(sla_properties, list):
        for item in sla_properties:
            if not isinstance(item, dict):
                continue
            if clean(item.get("property")).lower() != "freshness":
                continue
            raw_value = clean(item.get("value"))
            raw_unit = clean(item.get("unit")).lower()
            if raw_value and raw_unit:
                value = int(raw_value)
                if raw_unit in {"minute", "minutes"}:
                    return {"value": value, "unit": "minute"}
                if raw_unit in {"hour", "hours"}:
                    return {"value": value, "unit": "hour"}
                if raw_unit in {"day", "days"}:
                    return {"value": value, "unit": "day"}
                raise RuntimeError(f"Unsupported freshness unit for {path.name}: {raw_unit!r}")

    quality = contract.get("quality") if isinstance(contract.get("quality"), dict) else {}
    slos = quality.get("slos") if isinstance(quality.get("slos"), dict) else {}
    freshness_target = clean((slos.get("freshness") or {}).get("target"))
    if freshness_target:
        value, unit = parse_duration(freshness_target, field_name=f"{path.name} freshness target")
        return {"value": value, "unit": unit}
    return None


def build_openmetadata_import_contract(path: Path, contract: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    original_id = clean(contract.get("id"))
    metadata: dict[str, Any] = {
        "original_id": original_id,
        "contract_version": clean(contract.get("version")) or "1.0.0",
    }

    target = build_entity_target(path, contract)
    metadata["entity_target"] = target

    selected_schema = select_schema_object(path, contract, target)
    schema_properties = selected_schema.get("properties") if isinstance(selected_schema.get("properties"), list) else []

    transformed: dict[str, Any] = {
        "apiVersion": clean(contract.get("apiVersion")) or "v3.1.0",
        "kind": "DataContract",
        "id": stable_uuid(original_id or str(path.relative_to(path.parents[2]))),
        "name": clean(contract.get("name")) or derive_contract_name(path, contract, original_id),
        "version": metadata["contract_version"],
        "status": clean(contract.get("status")) or "active",
        "description": normalize_description(contract.get("description")),
        "tags": [clean(tag) for tag in (contract.get("tags") or []) if clean(tag)],
        "schema": [
            {
                "name": clean(selected_schema.get("name")) or target.table_name,
                "logicalType": clean(selected_schema.get("logicalType")) or "object",
                "physicalType": clean(selected_schema.get("physicalType")) or "table",
                "description": clean(selected_schema.get("description")) or None,
                "properties": schema_properties or None,
            }
        ],
    }

    raw_sla_properties = contract.get("slaProperties")
    if isinstance(raw_sla_properties, list):
        transformed["slaProperties"] = [item for item in raw_sla_properties if isinstance(item, dict)]

    metadata["max_latency"] = extract_max_latency(path, contract)

    if transformed.get("description") is None:
        transformed.pop("description")
    if not transformed.get("tags"):
        transformed.pop("tags", None)
    if transformed["schema"] and transformed["schema"][0].get("properties") is None:
        transformed["schema"][0].pop("properties", None)
    if not transformed.get("slaProperties"):
        transformed.pop("slaProperties", None)

    return transformed, metadata


def dump_transformed_contract(output_dir: Path, source_path: Path, contract: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / source_path.name
    output_path.write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    return output_path


def build_service_request(target: EntityTarget) -> dict[str, Any]:
    connection_config: dict[str, Any] = {
        "type": target.service_type,
        "hostPort": target.host_port,
        "username": "contract_seed",
        "database": target.database_name,
    }
    if target.service_type == "AzureSQL":
        connection_config["scheme"] = "mssql+pyodbc"
    elif target.service_type == "Mssql":
        connection_config["scheme"] = "mssql+pyodbc"
    elif target.service_type == "Postgres":
        connection_config["scheme"] = "postgresql+psycopg2"
    elif target.service_type == "Mysql":
        connection_config["scheme"] = "mysql+pymysql"

    return {
        "name": target.service_name,
        "serviceType": target.service_type,
        "description": "Service created by ODCS contract seeding",
        "connection": {"config": connection_config},
    }


def ensure_entity_hierarchy(api_base: str, token: str, target: EntityTarget, schema_properties: list[dict[str, Any]]) -> dict[str, Any]:
    service = request_json(api_base, "/v1/services/databaseServices", method="PUT", token=token, body=build_service_request(target))
    database = request_json(
        api_base,
        "/v1/databases",
        method="PUT",
        token=token,
        body={
            "name": target.database_name,
            "service": clean((service or {}).get("fullyQualifiedName")) or target.service_name,
            "description": "Database created by ODCS contract seeding",
        },
    )
    schema = request_json(
        api_base,
        "/v1/databaseSchemas",
        method="PUT",
        token=token,
        body={
            "name": target.schema_name,
            "database": clean((database or {}).get("fullyQualifiedName")) or target.database_fqn,
            "description": "Schema created by ODCS contract seeding",
        },
    )
    table = request_json(
        api_base,
        "/v1/tables",
        method="PUT",
        token=token,
        body={
            "name": target.table_name,
            "databaseSchema": clean((schema or {}).get("fullyQualifiedName")) or target.schema_fqn,
            "description": "Table created by ODCS contract seeding",
            "columns": [to_openmetadata_column(property_payload) for property_payload in schema_properties],
        },
    )
    if not isinstance(table, dict) or not clean(table.get("id")):
        raise RuntimeError(f"Failed to resolve OpenMetadata table for {target.table_fqn}")
    return table


def to_openmetadata_column(field_payload: dict[str, Any]) -> dict[str, Any]:
    logical_type = clean(field_payload.get("logicalType")).lower()
    data_type = {
        "integer": "INT",
        "long": "BIGINT",
        "number": "DECIMAL",
        "boolean": "BOOLEAN",
        "date": "DATE",
        "time": "TIME",
        "timestamp": "TIMESTAMP",
        "string": "VARCHAR",
        "object": "STRUCT",
        "array": "ARRAY",
    }.get(logical_type, "VARCHAR")

    column: dict[str, Any] = {
        "name": clean(field_payload.get("name")),
        "description": clean(field_payload.get("description")) or None,
        "dataType": data_type,
        "dataTypeDisplay": clean(field_payload.get("physicalType")) or data_type,
    }
    options = field_payload.get("logicalTypeOptions") if isinstance(field_payload.get("logicalTypeOptions"), dict) else {}
    data_length = default_column_length(field_payload, options)
    if data_length is not None and data_type in {"VARCHAR", "CHAR", "BINARY", "VARBINARY"}:
        column["dataLength"] = data_length
    if logical_type == "number":
        if options.get("precision") is not None:
            column["precision"] = int(options["precision"])
        if options.get("scale") is not None:
            column["scale"] = int(options["scale"])
    if field_payload.get("primaryKey"):
        column["constraint"] = "PRIMARY_KEY"
    elif field_payload.get("unique"):
        column["constraint"] = "UNIQUE"
    elif field_payload.get("required"):
        column["constraint"] = "NOT_NULL"
    return {key: value for key, value in column.items() if value is not None}


def ensure_contract_metadata(
    api_base: str,
    token: str,
    contract: dict[str, Any],
    *,
    original_id: str,
    contract_version: str,
    max_latency: dict[str, Any] | None,
) -> dict[str, Any]:
    contract_id = clean(contract.get("id"))
    if not contract_id:
        raise RuntimeError("Imported contract response does not include an id")

    current_sla = contract.get("sla") if isinstance(contract.get("sla"), dict) else {}
    desired_sla = dict(current_sla)
    if max_latency is not None:
        desired_sla["maxLatency"] = max_latency

    current_source_url = clean(contract.get("sourceUrl")) or None
    desired_source_url = original_id or current_source_url

    patch_body: list[dict[str, Any]] = []
    if desired_source_url and desired_source_url != current_source_url:
        patch_body.append(
            {
                "op": "replace" if current_source_url is not None else "add",
                "path": "/sourceUrl",
                "value": desired_source_url,
            }
        )
    if desired_sla != current_sla:
        patch_body.append(
            {
                "op": "replace" if current_sla.get("maxLatency") is not None else "add",
                "path": "/sla/maxLatency",
                "value": desired_sla["maxLatency"],
            }
        )

    if not patch_body:
        return contract

    updated = request_json(
        api_base,
        f"/v1/dataContracts/{parse.quote(contract_id, safe='')}",
        method="PATCH",
        token=token,
        body=patch_body,
        content_type="application/json-patch+json",
    )
    if not isinstance(updated, dict):
        raise RuntimeError(f"OpenMetadata patch response was not a contract object for {contract_id}")
    return updated


def seed_contract(api_base: str, token: str, source_path: Path, transformed_path: Path, transformed: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    target: EntityTarget = metadata["entity_target"]
    schema = transformed.get("schema") or []
    table_object = schema[0] if isinstance(schema, list) and schema else {}
    schema_properties = table_object.get("properties") if isinstance(table_object, dict) and isinstance(table_object.get("properties"), list) else []
    table = ensure_entity_hierarchy(api_base, token, target, schema_properties)
    entity_id = clean(table.get("id"))

    imported = request_json(
        api_base,
        "/v1/dataContracts/odcs/yaml",
        method="PUT",
        token=token,
        raw_body=transformed_path.read_text(encoding="utf-8"),
        params={
            "entityId": entity_id,
            "entityType": "table",
            "mode": "merge",
            "objectName": target.table_name,
        },
        content_type="application/yaml",
    )
    if not isinstance(imported, dict):
        raise RuntimeError(f"OpenMetadata contract import did not return a contract object for {source_path.name}")

    final_contract = ensure_contract_metadata(
        api_base,
        token,
        imported,
        original_id=metadata["original_id"],
        contract_version=metadata["contract_version"],
        max_latency=metadata.get("max_latency"),
    )
    return {
        "source": str(source_path),
        "transformed": str(transformed_path),
        "entity_fqn": target.table_fqn,
        "contract_id": clean(final_contract.get("id")),
        "contract_name": clean(final_contract.get("name")),
    }


def main() -> int:
    global SSL_CONTEXT

    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    contracts_dir = Path(args.contracts_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    api_base = normalize_endpoint(args.endpoint)
    SSL_CONTEXT = build_ssl_context(api_base, repo_root)

    token = clean(args.token)
    if not token and not args.dry_run:
        if not args.email or not (args.password or args.password_b64):
            raise RuntimeError(
                "OpenMetadata authentication requires either --token or repo-owned --email with --password/--password-b64"
            )
        token = login(api_base, args.email, args.password, args.password_b64)

    contract_files = discover_contract_files(contracts_dir)
    successes: list[dict[str, Any]] = []
    failures: list[tuple[Path, str]] = []
    seen_entities: dict[str, Path] = {}

    for source_path in contract_files:
        try:
            contract = load_yaml_file(source_path)
            require_supported_contract(source_path, contract)
            transformed, metadata = build_openmetadata_import_contract(source_path, contract)
            target: EntityTarget = metadata["entity_target"]
            if target.table_fqn in seen_entities and seen_entities[target.table_fqn] != source_path:
                raise RuntimeError(
                    f"Multiple ODCS files target the same OpenMetadata table {target.table_fqn}: "
                    f"{seen_entities[target.table_fqn]} and {source_path}"
                )
            seen_entities[target.table_fqn] = source_path

            transformed_path = dump_transformed_contract(output_dir, source_path, transformed)

            if args.dry_run:
                print(f"[dry-run] transformed {source_path} -> {transformed_path}")
                successes.append(
                    {
                        "source": str(source_path),
                        "transformed": str(transformed_path),
                        "entity_fqn": target.table_fqn,
                        "contract_id": transformed["id"],
                        "contract_name": transformed["name"],
                    }
                )
                continue

            result = seed_contract(api_base, token, source_path, transformed_path, transformed, metadata)
            print(
                f"[seeded] {source_path.name} -> {result['entity_fqn']} "
                f"(contract={result['contract_name']}, id={result['contract_id']})"
            )
            successes.append(result)
        except Exception as exc:  # noqa: BLE001
            failures.append((source_path, str(exc)))
            print(f"[error] {source_path}: {exc}", file=sys.stderr)
            if not args.continue_on_error:
                break

    print(json.dumps({"seeded": successes, "failures": [{"source": str(path), "error": message} for path, message in failures]}, indent=2))

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
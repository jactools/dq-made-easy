#!/usr/bin/env python3
"""Run the Logical Data Definitions to OpenMetadata pipeline.

This orchestrates the existing transformation script plus the validated import
steps that are available in this repository:

1. Transform the workbook into normalized CSV files.
2. Create or update glossaries and glossary terms in OpenMetadata.
3. Apply glossary-term tags to mapped columns.
4. Write a run report.

The BDE assignment output is included in the final report, but it is not pushed
into OpenMetadata because this repository does not yet define a verified target
entity model for those relationships.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, MutableMapping, Optional, Sequence, Set, Tuple
from urllib import error, parse, request

from openmetadata_tls import build_ssl_context


DEFAULT_STAGES = [
    "transform",
    "import-glossary",
    "preflight-mappings",
    "apply-mappings",
    "report",
]
SUPPORTED_STAGES = set(DEFAULT_STAGES)


@dataclass
class RunnerPaths:
    output_dir: Path
    glossary_csv: Path
    mappings_csv: Path
    bde_csv: Path
    transform_summary_md: Path
    runner_state_json: Path
    runner_report_json: Path
    runner_report_md: Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def log_progress(message: str) -> None:
    print(message, flush=True)


def default_login_email() -> str:
    return clean(os.environ.get("OM_EMAIL") or os.environ.get("OPENMETADATA_OIDC_SEED_USERNAME"))


def default_login_password() -> str:
    return clean(
        os.environ.get("OM_PASSWORD")
        or os.environ.get("OPENMETADATA_OIDC_SEED_PASSWORD")
        or os.environ.get("KEYCLOAK_SEEDED_USER_PASSWORD")
        or os.environ.get("KEYCLOAK_USER_PASSWORD")
    )


def clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_stages(value: str) -> List[str]:
    raw = [part.strip() for part in value.split(",") if part.strip()]
    if not raw:
        raise ValueError("At least one stage must be provided")
    if len(raw) == 1 and raw[0] == "all":
        return list(DEFAULT_STAGES)

    invalid = [stage for stage in raw if stage not in SUPPORTED_STAGES]
    if invalid:
        raise ValueError(
            f"Unsupported stages: {', '.join(invalid)}. Supported: {', '.join(DEFAULT_STAGES)}"
        )
    return raw


def slugify(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", clean(value).lower()).strip("_")
    if not normalized:
        normalized = fallback
    if normalized[0].isdigit():
        normalized = f"n_{normalized}"
    return normalized[:120]


def stable_suffix(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return digest[:8]


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [{key: clean(val) for key, val in row.items()} for row in reader]


def split_pipe_list(value: str) -> List[str]:
    items = []
    seen: Set[str] = set()
    for part in value.split("|"):
        cleaned = clean(part)
        lowered = cleaned.lower()
        if cleaned and lowered not in seen:
            seen.add(lowered)
            items.append(cleaned)
    return items


def normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", clean(value).lower())


def schema_aliases(schema_name: str) -> List[str]:
    value = clean(schema_name)
    aliases: List[str] = [value]
    lowered = value.lower()
    if lowered.startswith("schema_") and len(value) > len("schema_"):
        aliases.append(value[len("schema_") :])
    elif lowered.startswith("schema") and len(value) > len("schema"):
        aliases.append(value[len("schema") :].lstrip("_"))
    return [alias for alias in aliases if alias]


def normalize_endpoint(endpoint: str) -> Tuple[str, str]:
    base = endpoint.rstrip("/")
    if base.endswith("/api"):
        return base[: -len("/api")], base
    return base, f"{base}/api"


def resolve_paths(output_dir: Path) -> RunnerPaths:
    return RunnerPaths(
        output_dir=output_dir,
        glossary_csv=output_dir / "openmetadata_glossary_terms.csv",
        mappings_csv=output_dir / "openmetadata_column_mappings.csv",
        bde_csv=output_dir / "openmetadata_bde_assignments.csv",
        transform_summary_md=output_dir / "README.md",
        runner_state_json=output_dir / "openmetadata_runner_state.json",
        runner_report_json=output_dir / "openmetadata_runner_report.json",
        runner_report_md=output_dir / "openmetadata_runner_report.md",
    )


class OpenMetadataClient:
    def __init__(
        self,
        endpoint: str,
        timeout_seconds: int,
        token: str = "",
        email: str = "",
        password: str = "",
    ) -> None:
        self.base_url, self.api_base = normalize_endpoint(endpoint)
        self.timeout_seconds = timeout_seconds
        self.token = clean(token)
        self.email = clean(email)
        self.password = clean(password)
        self.ssl_context = build_ssl_context(endpoint, Path(__file__).resolve().parents[2])

    def is_healthy(self) -> bool:
        try:
            payload = self.request_json("GET", "/v1/system/version", authenticated=False)
            return bool(payload)
        except Exception:
            return False

    def ensure_token(self) -> str:
        if self.token:
            return self.token
        if not self.email or not self.password:
            raise RuntimeError(
                "OpenMetadata authentication requires either --token or both --email and --password"
            )

        encoded_password = base64.b64encode(self.password.encode("utf-8")).decode("ascii")
        payload = None
        login_errors: List[str] = []
        for login_path in ["/v1/users/login", "/v1/auth/login"]:
            try:
                payload = self.request_json(
                    "POST",
                    login_path,
                    body={"email": self.email, "password": encoded_password},
                    authenticated=False,
                )
                break
            except Exception as exc:
                login_errors.append(f"{login_path}: {exc}")

        token = clean((payload or {}).get("accessToken"))
        if not token:
            raise RuntimeError(
                "OpenMetadata login did not return an access token. "
                + " | ".join(login_errors)
            )
        self.token = token
        return token

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Any] = None,
        authenticated: bool = True,
        allow_404: bool = False,
    ) -> Any:
        query = f"?{parse.urlencode(params, doseq=True)}" if params else ""
        url = f"{self.api_base}{path}{query}"

        headers = {"Accept": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.ensure_token()}"

        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")

        req = request.Request(url=url, data=data, headers=headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=self.timeout_seconds, context=self.ssl_context) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return None
                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return json.loads(raw)
                return raw
        except error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404 and allow_404:
                return None
            raise RuntimeError(
                f"OpenMetadata API {method.upper()} {path} failed with {exc.code}: {body_text[:400]}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"Failed to reach OpenMetadata at {url}: {exc}") from exc

    def create_or_update_glossary(self, name: str, display_name: str, description: str) -> Dict[str, Any]:
        return self.request_json(
            "PUT",
            "/v1/glossaries",
            body={
                "name": name,
                "displayName": display_name,
                "description": description,
                "mutuallyExclusive": False,
            },
        )

    def create_or_update_term(
        self,
        *,
        name: str,
        display_name: str,
        description: str,
        glossary_fqn: str,
        synonyms: Sequence[str],
        extension: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = {
            "name": name,
            "displayName": display_name,
            "description": description,
            "glossary": glossary_fqn,
            "mutuallyExclusive": False,
        }
        if synonyms:
            payload["synonyms"] = list(synonyms)
        if extension:
            payload["extension"] = extension

        try:
            return self.request_json("PUT", "/v1/glossaryTerms", body=payload)
        except RuntimeError as exc:
            # Some OpenMetadata deployments do not define custom glossary-term
            # extension fields (for example assetId). Retry without extension.
            message = str(exc)
            if extension and (
                "Unknown custom field" in message
                or "Invalid custom field" in message
                or "failed with 400" in message
            ):
                payload.pop("extension", None)
                return self.request_json("PUT", "/v1/glossaryTerms", body=payload)
            raise

    def get_term_by_fqn(self, term_fqn: str) -> Optional[Dict[str, Any]]:
        encoded = parse.quote(term_fqn, safe="")
        return self.request_json("GET", f"/v1/glossaryTerms/name/{encoded}", allow_404=True)

    def get_table_by_fqn(self, table_fqn: str) -> Optional[Dict[str, Any]]:
        encoded = parse.quote(table_fqn, safe="")
        return self.request_json(
            "GET",
            f"/v1/tables/name/{encoded}",
            params={"fields": "columns,tags"},
            allow_404=True,
        )

    def update_column_tags(self, column_fqn: str, tags: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        encoded = parse.quote(column_fqn, safe="")
        return self.request_json(
            "PUT",
            f"/v1/columns/name/{encoded}",
            params={"entityType": "table"},
            body={"tags": list(tags)},
        )

    def list_tables(self, *, fields: str = "columns", limit: int = 100) -> List[Dict[str, Any]]:
        all_rows: List[Dict[str, Any]] = []
        after: Optional[str] = None
        page = 1

        while True:
            params: Dict[str, Any] = {"fields": fields, "limit": limit}
            if after:
                params["after"] = after

            suffix = f" after={after}" if after else ""
            log_progress(f"[catalog] fetching table page {page} (fields={fields}, limit={limit}{suffix})")

            payload = self.request_json("GET", "/v1/tables", params=params)
            rows = (payload or {}).get("data") or []
            all_rows.extend(rows)
            log_progress(
                f"[catalog] fetched table page {page}: {len(rows)} rows (total {len(all_rows)})"
            )

            paging = (payload or {}).get("paging") or {}
            after = clean(paging.get("after"))
            if not after:
                break
            page += 1

        return all_rows


def run_transform_stage(args: argparse.Namespace, repo_root: Path) -> Dict[str, Any]:
    output_dir = Path(args.output_dir).expanduser()
    existing_outputs = [
        output_dir / "openmetadata_glossary_terms.csv",
        output_dir / "openmetadata_column_mappings.csv",
        output_dir / "openmetadata_bde_assignments.csv",
    ]

    if not args.input:
        input_dir = Path(args.input_dir).expanduser()
        workbook_candidates = [
            p
            for p in input_dir.glob("*.xlsx")
            if p.is_file() and not p.name.startswith("~$")
        ]
        if not workbook_candidates and all(path.exists() for path in existing_outputs):
            return {
                "skipped": True,
                "reason": "Reused existing normalized OpenMetadata CSV outputs because no source workbook was available.",
                "output_dir": str(output_dir),
            }

    script_path = repo_root / "dq-metadata" / "scripts" / "transform_ldd_to_openmetadata.py"
    command = [sys.executable, str(script_path)]
    if args.input:
        command.extend(["--input", args.input])
    command.extend(["--input-dir", args.input_dir])
    command.extend(["--output-dir", args.output_dir])
    command.extend(["--service-name", args.service_name])
    command.extend(["--database-name", args.database_name])

    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return {
        "command": command,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def build_glossary_plan(rows: Sequence[Dict[str, str]]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    glossary_plan: Dict[str, Dict[str, Any]] = {}
    glossary_name_usage: Dict[str, str] = {}
    term_plan: Dict[str, Dict[str, Any]] = {}
    used_term_names: Dict[str, Dict[str, str]] = defaultdict(dict)

    for row in rows:
        glossary_display = row.get("glossary_name") or "Logical Data Dictionary"
        glossary_slug = slugify(glossary_display, "logical_data_dictionary")
        existing_display = glossary_name_usage.get(glossary_slug)
        if existing_display and existing_display != glossary_display:
            glossary_slug = f"{glossary_slug}_{stable_suffix(glossary_display)}"
        glossary_name_usage[glossary_slug] = glossary_display

        glossary = glossary_plan.setdefault(
            glossary_display,
            {
                "display_name": glossary_display,
                "name": glossary_slug,
                "description": f"Imported from the Logical Data Definitions pipeline for {glossary_display}.",
            },
        )

        row_key = row.get("asset_id") or row.get("term_name") or row.get("display_name")
        if not row_key:
            continue

        base_name = slugify(row.get("term_name") or row.get("display_name") or row_key, "term")
        glossary_key = glossary["display_name"]
        scoped_names = used_term_names[glossary_key]
        chosen_name = base_name
        current_owner = scoped_names.get(base_name)
        if current_owner and current_owner != row_key:
            chosen_name = f"{base_name}_{slugify(row.get('asset_id') or stable_suffix(row_key), 'term')}"
        scoped_names[chosen_name] = row_key

        term_plan[row_key] = {
            "row_key": row_key,
            "asset_id": row.get("asset_id", ""),
            "glossary_display_name": glossary["display_name"],
            "glossary_name": glossary["name"],
            "term_name": chosen_name,
            "display_name": row.get("display_name") or row.get("term_name") or row_key,
            "source_term_name": row.get("term_name") or row.get("display_name") or row_key,
            "description": row.get("description") or f"Imported logical term: {row.get('display_name') or row_key}",
            "synonyms": split_pipe_list(row.get("synonyms", "")),
            "extension": {
                "assetId": row.get("asset_id", ""),
                "logicalDataType": row.get("logical_data_type", ""),
                "sourceStatus": row.get("status", ""),
                "domainValues": row.get("domain_values", ""),
                "notes": row.get("notes", ""),
                "source": "ldd_pipeline",
            },
        }

    return glossary_plan, term_plan


def load_existing_state(paths: RunnerPaths) -> Dict[str, Any]:
    if not paths.runner_state_json.exists():
        return {}
    return json.loads(paths.runner_state_json.read_text(encoding="utf-8"))


def write_state(paths: RunnerPaths, state: Dict[str, Any]) -> None:
    paths.runner_state_json.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def import_glossary_stage(
    client: OpenMetadataClient,
    glossary_rows: Sequence[Dict[str, str]],
    *,
    dry_run: bool,
    continue_on_error: bool,
    state: MutableMapping[str, Any],
    limit_terms: int,
) -> Dict[str, Any]:
    glossary_plan, term_plan = build_glossary_plan(glossary_rows)
    glossary_results: Dict[str, Dict[str, Any]] = {}
    term_results: Dict[str, Dict[str, Any]] = {}
    failures: List[Dict[str, str]] = []

    log_progress(
        f"[import-glossary] starting: {len(glossary_plan)} glossaries, {len(term_plan)} candidate terms"
    )

    for glossary_display, glossary_meta in glossary_plan.items():
        glossary_fqn = glossary_meta["name"]
        if dry_run:
            glossary_results[glossary_display] = {
                **glossary_meta,
                "id": "",
                "fqn": glossary_fqn,
                "status": "planned",
            }
            continue
        try:
            entity = client.create_or_update_glossary(
                name=glossary_meta["name"],
                display_name=glossary_meta["display_name"],
                description=glossary_meta["description"],
            )
            glossary_results[glossary_display] = {
                **glossary_meta,
                "id": clean(entity.get("id")),
                "fqn": clean(entity.get("fullyQualifiedName")) or glossary_fqn,
                "status": "applied",
            }
        except Exception as exc:
            failures.append({"stage": "import-glossary", "item": glossary_display, "error": str(exc)})
            if not continue_on_error:
                raise

    term_items = list(term_plan.values())
    if limit_terms > 0:
        term_items = term_items[:limit_terms]

    total_terms = len(term_items)
    if total_terms:
        log_progress(f"[import-glossary] importing {total_terms} terms")

    for index, term_meta in enumerate(term_items, start=1):
        glossary_info = glossary_results.get(term_meta["glossary_display_name"])
        if not glossary_info:
            failures.append(
                {
                    "stage": "import-glossary",
                    "item": term_meta["display_name"],
                    "error": f"Glossary was not available for {term_meta['glossary_display_name']}",
                }
            )
            if not continue_on_error:
                raise RuntimeError(f"Missing glossary for term {term_meta['display_name']}")
            continue

        glossary_fqn = glossary_info["fqn"]
        resolved_term_fqn = f"{glossary_fqn}.{term_meta['term_name']}"
        term_record = {
            **term_meta,
            "glossary_fqn": glossary_fqn,
            "fqn": resolved_term_fqn,
            "id": "",
            "status": "planned" if dry_run else "pending",
        }
        try:
            if not dry_run:
                entity = client.create_or_update_term(
                    name=term_meta["term_name"],
                    display_name=term_meta["display_name"],
                    description=term_meta["description"],
                    glossary_fqn=glossary_fqn,
                    synonyms=term_meta["synonyms"],
                    extension=term_meta["extension"],
                )
                term_record["id"] = clean(entity.get("id"))
                term_record["fqn"] = clean(entity.get("fullyQualifiedName")) or resolved_term_fqn
                term_record["status"] = "applied"
            term_results[term_meta["row_key"]] = term_record
        except Exception as exc:
            failures.append(
                {"stage": "import-glossary", "item": term_meta["display_name"], "error": str(exc)}
            )
            if not continue_on_error:
                raise

        if index == total_terms or index == 1 or index % 100 == 0:
            log_progress(f"[import-glossary] processed {index}/{total_terms} terms")

    result = {
        "dry_run": dry_run,
        "glossary_count": len(glossary_results),
        "term_count": len(term_results),
        "failures": failures,
        "glossaries": glossary_results,
        "terms": term_results,
    }

    state["glossary_import"] = {
        "generated_at": utc_now_iso(),
        **result,
    }
    return result


def table_fqn_from_column_fqn(column_fqn: str) -> str:
    parts = column_fqn.split(".")
    if len(parts) < 5:
        raise ValueError(f"Column FQN does not look like service.database.schema.table.column: {column_fqn}")
    return ".".join(parts[:-1])


def table_pairs_from_mapping_rows(mapping_rows: Sequence[Dict[str, str]]) -> Set[Tuple[str, str]]:
    pairs: Set[Tuple[str, str]] = set()
    for row in mapping_rows:
        schema_name = clean(row.get("schema_name"))
        table_name = clean(row.get("table_name"))
        if schema_name and table_name:
            pairs.add((schema_name, table_name))
    return pairs


def table_pairs_from_catalog_tables(tables: Sequence[Dict[str, Any]]) -> Set[Tuple[str, str]]:
    pairs: Set[Tuple[str, str]] = set()
    for table in tables:
        fqn = clean(table.get("fullyQualifiedName"))
        parts = fqn.split(".")
        if len(parts) < 4:
            continue
        schema_name = clean(parts[-2])
        table_name = clean(parts[-1])
        if schema_name and table_name:
            pairs.add((schema_name, table_name))
    return pairs


def align_mapping_rows_to_catalog(
    mapping_rows: Sequence[Dict[str, str]],
    catalog_tables: Sequence[Dict[str, Any]],
    *,
    state: MutableMapping[str, Any],
) -> List[Dict[str, str]]:
    catalog_pairs = table_pairs_from_catalog_tables(catalog_tables)
    original_pairs = table_pairs_from_mapping_rows(mapping_rows)
    aligned_rows: List[Dict[str, str]] = []
    aligned_pairs: Set[Tuple[str, str]] = set()
    dropped_pairs: Set[Tuple[str, str]] = set()
    dropped_rows = 0

    for row in mapping_rows:
        schema_name = clean(row.get("schema_name"))
        table_name = clean(row.get("table_name"))
        pair = (schema_name, table_name)
        if schema_name and table_name and pair in catalog_pairs:
            aligned_rows.append(dict(row))
            aligned_pairs.add(pair)
        else:
            dropped_rows += 1
            if schema_name and table_name:
                dropped_pairs.add(pair)

    dropped_schema_counts: Dict[str, int] = {}
    for schema_name, _ in dropped_pairs:
        dropped_schema_counts[schema_name] = dropped_schema_counts.get(schema_name, 0) + 1

    state["mapping_alignment"] = {
        "generated_at": utc_now_iso(),
        "input_row_count": len(mapping_rows),
        "aligned_row_count": len(aligned_rows),
        "dropped_row_count": dropped_rows,
        "input_distinct_schema_table": len(original_pairs),
        "aligned_distinct_schema_table": len(aligned_pairs),
        "dropped_distinct_schema_table": len(dropped_pairs),
        "catalog_schemas": sorted({schema for schema, _ in catalog_pairs}),
        "top_dropped_schemas": [
            {"schema": schema_name, "dropped_tables": count}
            for schema_name, count in sorted(
                dropped_schema_counts.items(), key=lambda item: (-item[1], item[0])
            )[:12]
        ],
    }

    return aligned_rows


def mapping_preflight_stage(
    *,
    mapping_rows: Sequence[Dict[str, str]],
    catalog_tables: Sequence[Dict[str, Any]],
    state: MutableMapping[str, Any],
    min_mapping_coverage: float,
    fail_on_low_coverage: bool,
) -> Dict[str, Any]:
    mapping_pairs = table_pairs_from_mapping_rows(mapping_rows)
    catalog_pairs = table_pairs_from_catalog_tables(catalog_tables)

    log_progress(
        f"[preflight-mappings] comparing {len(mapping_pairs)} mapping schema.table pairs against {len(catalog_pairs)} catalog pairs"
    )

    present_pairs = mapping_pairs & catalog_pairs
    missing_pairs = mapping_pairs - catalog_pairs

    total_mapping_pairs = len(mapping_pairs)
    coverage_ratio = (len(present_pairs) / total_mapping_pairs) if total_mapping_pairs else 1.0

    missing_schema_counts: Dict[str, int] = {}
    for schema_name, _ in missing_pairs:
        missing_schema_counts[schema_name] = missing_schema_counts.get(schema_name, 0) + 1

    top_missing_schemas = [
        {"schema": schema_name, "missing_tables": count}
        for schema_name, count in sorted(
            missing_schema_counts.items(), key=lambda item: (-item[1], item[0])
        )[:12]
    ]

    missing_samples = [
        {"schema": schema_name, "table": table_name}
        for schema_name, table_name in sorted(missing_pairs)[:20]
    ]

    result = {
        "generated_at": utc_now_iso(),
        "mapping_distinct_schema_table": total_mapping_pairs,
        "catalog_distinct_schema_table": len(catalog_pairs),
        "present_schema_table": len(present_pairs),
        "missing_schema_table": len(missing_pairs),
        "coverage_ratio": coverage_ratio,
        "coverage_percent": round(coverage_ratio * 100.0, 3),
        "min_mapping_coverage": min_mapping_coverage,
        "catalog_schemas": sorted({schema for schema, _ in catalog_pairs}),
        "top_missing_schemas": top_missing_schemas,
        "sample_missing_pairs": missing_samples,
    }

    state["mapping_preflight"] = result

    log_progress(
        "[preflight-mappings] coverage "
        f"{result['coverage_percent']}% ({len(present_pairs)}/{total_mapping_pairs or 0} present pairs)"
    )

    if fail_on_low_coverage and total_mapping_pairs > 0 and coverage_ratio < min_mapping_coverage:
        raise RuntimeError(
            "Mapping preflight failed: coverage below threshold. "
            f"Required >= {min_mapping_coverage:.3f}, actual {coverage_ratio:.3f} "
            f"({len(present_pairs)}/{total_mapping_pairs} schema.table pairs). "
            "This usually means OpenMetadata catalog ingestion does not contain the schemas/tables "
            "referenced by the mapping CSV (for example only `public` exists while mappings target `Schema_*`)."
        )

    return result


def split_column_fqn(column_fqn: str) -> Optional[Tuple[str, str, str, str, str]]:
    parts = column_fqn.split(".")
    if len(parts) < 5:
        return None
    service, database, schema, table = parts[0], parts[1], parts[2], parts[3]
    column = ".".join(parts[4:])
    return service, database, schema, table, column


def build_lookup_keys(column_fqn: str) -> Set[str]:
    split = split_column_fqn(column_fqn)
    if not split:
        return set()
    service, database, schema, table, column = split

    service_norm = normalize_identifier(service)
    database_norm = normalize_identifier(database)
    table_norm = normalize_identifier(table)
    column_norm = normalize_identifier(column)
    if not (service_norm and database_norm and table_norm and column_norm):
        return set()

    keys: Set[str] = set()
    for schema_candidate in schema_aliases(schema):
        schema_norm = normalize_identifier(schema_candidate)
        if not schema_norm:
            continue
        keys.add("|".join([service_norm, database_norm, schema_norm, table_norm, column_norm]))
    return keys


def build_column_fqn_index(tables: Sequence[Dict[str, Any]]) -> Dict[str, Set[str]]:
    index: Dict[str, Set[str]] = defaultdict(set)
    for table in tables:
        table_fqn = clean(table.get("fullyQualifiedName"))
        table_split = split_column_fqn(f"{table_fqn}.placeholder")
        if not table_split:
            continue
        service, database, schema, table_name, _ = table_split
        service_norm = normalize_identifier(service)
        database_norm = normalize_identifier(database)
        table_norm = normalize_identifier(table_name)
        if not (service_norm and database_norm and table_norm):
            continue

        schema_norm_candidates = {normalize_identifier(alias) for alias in schema_aliases(schema)}
        schema_norm_candidates = {item for item in schema_norm_candidates if item}
        if not schema_norm_candidates:
            continue

        for column in iter_columns(table.get("columns") or []):
            column_fqn = clean(column.get("fullyQualifiedName"))
            if not column_fqn:
                continue
            column_name = clean(column.get("name")) or split_column_fqn(column_fqn)[-1]
            column_norm = normalize_identifier(column_name)
            if not column_norm:
                continue
            for schema_norm in schema_norm_candidates:
                key = "|".join([service_norm, database_norm, schema_norm, table_norm, column_norm])
                index[key].add(column_fqn)
    return index


def resolve_column_fqn_via_index(
    column_fqn: str,
    column_index: Dict[str, Set[str]],
) -> Tuple[Optional[str], List[str]]:
    matches: Set[str] = set()
    for key in build_lookup_keys(column_fqn):
        matches.update(column_index.get(key) or set())
    if not matches:
        return None, []
    ordered = sorted(matches)
    if len(ordered) == 1:
        return ordered[0], ordered
    return None, ordered


def iter_columns(columns: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    for column in columns or []:
        yield column
        children = column.get("children") or []
        yield from iter_columns(children)


def find_column(table_payload: Dict[str, Any], column_fqn: str) -> Optional[Dict[str, Any]]:
    for column in iter_columns(table_payload.get("columns") or []):
        if clean(column.get("fullyQualifiedName")) == column_fqn:
            return column
    return None


def normalize_tag(tag: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "tagFQN": clean(tag.get("tagFQN")),
        "source": clean(tag.get("source")) or "Classification",
        "labelType": clean(tag.get("labelType")) or "Manual",
        "state": clean(tag.get("state")) or "Confirmed",
    }
    name = clean(tag.get("name"))
    if name:
        payload["name"] = name
    return payload


def resolve_term_fqns(
    client: OpenMetadataClient,
    *,
    glossary_rows: Sequence[Dict[str, str]],
    import_result: Dict[str, Any],
    dry_run: bool,
) -> Dict[str, str]:
    resolved: Dict[str, str] = {}
    if import_result.get("terms"):
        for row_key, term_meta in import_result["terms"].items():
            term_fqn = clean(term_meta.get("fqn"))
            if term_fqn:
                resolved[row_key] = term_fqn

    if resolved:
        return resolved

    _, term_plan = build_glossary_plan(glossary_rows)
    for row_key, term_meta in term_plan.items():
        term_fqn = f"{term_meta['glossary_name']}.{term_meta['term_name']}"
        if dry_run:
            resolved[row_key] = term_fqn
            continue
        entity = client.get_term_by_fqn(term_fqn)
        if entity:
            resolved[row_key] = clean(entity.get("fullyQualifiedName")) or term_fqn
    return resolved


def apply_mappings_stage(
    client: OpenMetadataClient,
    *,
    glossary_rows: Sequence[Dict[str, str]],
    mapping_rows: Sequence[Dict[str, str]],
    import_result: Dict[str, Any],
    dry_run: bool,
    continue_on_error: bool,
    limit_mappings: int,
    state: MutableMapping[str, Any],
) -> Dict[str, Any]:
    term_fqns = resolve_term_fqns(client, glossary_rows=glossary_rows, import_result=import_result, dry_run=dry_run)

    requested_tags: Dict[str, Set[str]] = defaultdict(set)
    unresolved_terms: List[Dict[str, str]] = []

    for row in mapping_rows:
        column_fqn = row.get("openmetadata_column_fqn", "")
        row_key = row.get("asset_id") or row.get("logical_name") or row.get("logical_full_name")
        term_fqn = term_fqns.get(row_key, "")
        if not column_fqn:
            continue
        if not term_fqn:
            unresolved_terms.append(
                {
                    "asset_id": row.get("asset_id", ""),
                    "logical_name": row.get("logical_name", ""),
                    "column_fqn": column_fqn,
                    "reason": "No glossary term FQN was resolved for this mapping",
                }
            )
            continue
        requested_tags[column_fqn].add(term_fqn)

    column_items = sorted(requested_tags.items())
    if limit_mappings > 0:
        column_items = column_items[:limit_mappings]

    total_columns = len(column_items)
    log_progress(f"[apply-mappings] starting: {total_columns} columns requested")

    table_cache: Dict[str, Dict[str, Any]] = {}
    column_index: Optional[Dict[str, Set[str]]] = None
    updates: List[Dict[str, Any]] = []
    failures: List[Dict[str, str]] = []
    unresolved_targets: List[Dict[str, str]] = []
    skipped = 0

    for index, (column_fqn, term_set) in enumerate(column_items, start=1):
        resolved_column_fqn = column_fqn
        table_fqn = table_fqn_from_column_fqn(resolved_column_fqn)
        try:
            table_payload = table_cache.get(table_fqn)
            if table_payload is None:
                table_payload = client.get_table_by_fqn(table_fqn)
                if table_payload:
                    table_cache[table_fqn] = table_payload

            if not table_payload:
                if column_index is None:
                    catalog_tables = client.list_tables(fields="columns", limit=100)
                    column_index = build_column_fqn_index(catalog_tables)
                reconciled_fqn, candidates = resolve_column_fqn_via_index(column_fqn, column_index)
                if reconciled_fqn:
                    resolved_column_fqn = reconciled_fqn
                    table_fqn = table_fqn_from_column_fqn(resolved_column_fqn)
                    table_payload = table_cache.get(table_fqn)
                    if table_payload is None:
                        table_payload = client.get_table_by_fqn(table_fqn)
                        if table_payload:
                            table_cache[table_fqn] = table_payload
                elif candidates:
                    unresolved_targets.append(
                        {
                            "column_fqn": column_fqn,
                            "table_fqn": table_fqn,
                            "reason": "Target column resolved to multiple OpenMetadata candidates",
                            "candidates": ", ".join(candidates[:3]),
                        }
                    )
                    continue

            if not table_payload:
                unresolved_targets.append(
                    {
                        "column_fqn": column_fqn,
                        "table_fqn": table_fqn,
                        "reason": "Target table was not found in OpenMetadata",
                    }
                )
                continue

            column_payload = find_column(table_payload, resolved_column_fqn)
            if not column_payload:
                unresolved_targets.append(
                    {
                        "column_fqn": column_fqn,
                        "table_fqn": table_fqn,
                        "reason": "Target column was not found in OpenMetadata table payload",
                    }
                )
                continue

            existing_tags = [normalize_tag(tag) for tag in (column_payload.get("tags") or [])]
            merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
            for tag in existing_tags:
                key = (tag["tagFQN"], tag["source"])
                merged[key] = tag
            for term_fqn in sorted(term_set):
                key = (term_fqn, "Glossary")
                merged[key] = {
                    "tagFQN": term_fqn,
                    "source": "Glossary",
                    "labelType": "Manual",
                    "state": "Confirmed",
                }

            new_tags = list(merged.values())
            existing_keys = {(tag["tagFQN"], tag["source"]) for tag in existing_tags}
            new_keys = {(tag["tagFQN"], tag["source"]) for tag in new_tags}
            if existing_keys == new_keys:
                skipped += 1
                updates.append(
                    {
                        "column_fqn": resolved_column_fqn,
                        "source_column_fqn": column_fqn,
                        "table_fqn": table_fqn,
                        "status": "unchanged",
                        "glossary_terms": sorted(term_set),
                    }
                )
                continue

            if not dry_run:
                client.update_column_tags(resolved_column_fqn, new_tags)
                table_cache.pop(table_fqn, None)

            updates.append(
                {
                    "column_fqn": resolved_column_fqn,
                    "source_column_fqn": column_fqn,
                    "table_fqn": table_fqn,
                    "status": "planned" if dry_run else "applied",
                    "existing_tag_count": len(existing_tags),
                    "updated_tag_count": len(new_tags),
                    "glossary_terms": sorted(term_set),
                }
            )
        except Exception as exc:
            failures.append({"stage": "apply-mappings", "item": column_fqn, "error": str(exc)})
            if not continue_on_error:
                raise

        if total_columns and (index == total_columns or index == 1 or index % 250 == 0):
            log_progress(f"[apply-mappings] processed {index}/{total_columns} columns")

    result = {
        "dry_run": dry_run,
        "requested_columns": len(column_items),
        "applied_or_planned": len(updates),
        "unchanged": skipped,
        "unresolved_terms": unresolved_terms,
        "unresolved_targets": unresolved_targets,
        "failures": failures,
        "updates": updates,
    }
    state["column_mapping"] = {"generated_at": utc_now_iso(), **result}
    return result


def build_report(
    *,
    stages: Sequence[str],
    paths: RunnerPaths,
    state: Dict[str, Any],
    transform_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    glossary_rows = read_csv_rows(paths.glossary_csv) if paths.glossary_csv.exists() else []
    mapping_rows = read_csv_rows(paths.mappings_csv) if paths.mappings_csv.exists() else []
    bde_rows = read_csv_rows(paths.bde_csv) if paths.bde_csv.exists() else []

    report = {
        "generated_at": utc_now_iso(),
        "stages": list(stages),
        "files": {
            "glossary_csv": str(paths.glossary_csv),
            "mapping_csv": str(paths.mappings_csv),
            "bde_csv": str(paths.bde_csv),
            "transform_summary": str(paths.transform_summary_md),
        },
        "row_counts": {
            "glossary_terms": len(glossary_rows),
            "column_mappings": len(mapping_rows),
            "bde_assignments": len(bde_rows),
        },
        "transform": transform_result or {},
        "glossary_import": state.get("glossary_import", {}),
        "mapping_alignment": state.get("mapping_alignment", {}),
        "mapping_preflight": state.get("mapping_preflight", {}),
        "column_mapping": state.get("column_mapping", {}),
        "notes": [
            "BDE assignments are included in the generated CSV output and this report.",
            "The runner does not push BDE assignments into OpenMetadata because no verified repository-specific target model is defined for that relationship yet.",
        ],
    }
    return report


def write_report(paths: RunnerPaths, report: Dict[str, Any]) -> None:
    paths.runner_report_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# OpenMetadata LDD Runner Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Stages: `{', '.join(report['stages'])}`",
        f"- Glossary CSV rows: `{report['row_counts']['glossary_terms']}`",
        f"- Column mapping CSV rows: `{report['row_counts']['column_mappings']}`",
        f"- BDE assignment CSV rows: `{report['row_counts']['bde_assignments']}`",
        "",
        "## Glossary Import",
        "",
    ]

    glossary_import = report.get("glossary_import") or {}
    if glossary_import:
        lines.extend(
            [
                f"- Dry run: `{glossary_import.get('dry_run', False)}`",
                f"- Glossaries processed: `{glossary_import.get('glossary_count', 0)}`",
                f"- Terms processed: `{glossary_import.get('term_count', 0)}`",
                f"- Failures: `{len(glossary_import.get('failures', []))}`",
            ]
        )
    else:
        lines.append("- Not executed")

    mapping_preflight = report.get("mapping_preflight") or {}
    lines.extend(["", "## Mapping Preflight", ""])
    if mapping_preflight:
        lines.extend(
            [
                f"- Distinct mapping schema.table pairs: `{mapping_preflight.get('mapping_distinct_schema_table', 0)}`",
                f"- Distinct catalog schema.table pairs: `{mapping_preflight.get('catalog_distinct_schema_table', 0)}`",
                f"- Present pairs: `{mapping_preflight.get('present_schema_table', 0)}`",
                f"- Missing pairs: `{mapping_preflight.get('missing_schema_table', 0)}`",
                f"- Coverage: `{mapping_preflight.get('coverage_percent', 0)}%`",
                f"- Minimum required coverage: `{mapping_preflight.get('min_mapping_coverage', 0)}`",
            ]
        )
    else:
        lines.append("- Not executed")

    mapping_alignment = report.get("mapping_alignment") or {}
    lines.extend(["", "## Mapping Alignment", ""])
    if mapping_alignment:
        lines.extend(
            [
                f"- Input mapping rows: `{mapping_alignment.get('input_row_count', 0)}`",
                f"- Aligned mapping rows: `{mapping_alignment.get('aligned_row_count', 0)}`",
                f"- Dropped mapping rows: `{mapping_alignment.get('dropped_row_count', 0)}`",
                f"- Input distinct schema.table pairs: `{mapping_alignment.get('input_distinct_schema_table', 0)}`",
                f"- Aligned distinct schema.table pairs: `{mapping_alignment.get('aligned_distinct_schema_table', 0)}`",
                f"- Dropped distinct schema.table pairs: `{mapping_alignment.get('dropped_distinct_schema_table', 0)}`",
            ]
        )
    else:
        lines.append("- Not executed")

    lines.extend(["", "## Column Mapping", ""])

    column_mapping = report.get("column_mapping") or {}
    if column_mapping:
        lines.extend(
            [
                f"- Dry run: `{column_mapping.get('dry_run', False)}`",
                f"- Columns requested: `{column_mapping.get('requested_columns', 0)}`",
                f"- Applied or planned updates: `{column_mapping.get('applied_or_planned', 0)}`",
                f"- Unchanged columns: `{column_mapping.get('unchanged', 0)}`",
                f"- Unresolved mappings: `{len(column_mapping.get('unresolved_terms', []))}`",
                f"- Missing target entities: `{len(column_mapping.get('unresolved_targets', []))}`",
                f"- Failures: `{len(column_mapping.get('failures', []))}`",
            ]
        )
    else:
        lines.append("- Not executed")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- BDE assignments remain report-only in this runner.",
            "- Column mapping updates preserve existing column tags and add glossary-term tags on top.",
        ]
    )
    paths.runner_report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_report_summary(report: Dict[str, Any], paths: RunnerPaths) -> None:
    row_counts = report.get("row_counts") or {}
    glossary_import = report.get("glossary_import") or {}
    mapping_alignment = report.get("mapping_alignment") or {}
    mapping_preflight = report.get("mapping_preflight") or {}
    column_mapping = report.get("column_mapping") or {}

    print("LDD runner summary:")
    print(f"- Report JSON: {paths.runner_report_json}")
    print(f"- Report Markdown: {paths.runner_report_md}")
    print(
        "- Rows: "
        f"glossary_terms={row_counts.get('glossary_terms', 0)} "
        f"column_mappings={row_counts.get('column_mappings', 0)} "
        f"bde_assignments={row_counts.get('bde_assignments', 0)}"
    )

    if glossary_import:
        print(
            "- Glossary import: "
            f"glossaries={glossary_import.get('glossary_count', 0)} "
            f"terms={glossary_import.get('term_count', 0)} "
            f"failures={len(glossary_import.get('failures', []))}"
        )

    if mapping_preflight:
        print(
            "- Mapping preflight: "
            f"coverage={mapping_preflight.get('coverage_percent', 0)}% "
            f"present={mapping_preflight.get('present_schema_table', 0)}/"
            f"{mapping_preflight.get('mapping_distinct_schema_table', 0)} "
            f"missing={mapping_preflight.get('missing_schema_table', 0)}"
        )

    if mapping_alignment:
        print(
            "- Mapping alignment: "
            f"aligned_rows={mapping_alignment.get('aligned_row_count', 0)} "
            f"dropped_rows={mapping_alignment.get('dropped_row_count', 0)} "
            f"aligned_pairs={mapping_alignment.get('aligned_distinct_schema_table', 0)}/"
            f"{mapping_alignment.get('input_distinct_schema_table', 0)}"
        )

    if column_mapping:
        print(
            "- Column mapping: "
            f"applied_or_planned={column_mapping.get('applied_or_planned', 0)} "
            f"unchanged={column_mapping.get('unchanged', 0)} "
            f"unresolved_terms={len(column_mapping.get('unresolved_terms', []))} "
            f"unresolved_targets={len(column_mapping.get('unresolved_targets', []))} "
            f"failures={len(column_mapping.get('failures', []))}"
        )


def ensure_required_outputs(paths: RunnerPaths) -> None:
    missing = [
        str(path)
        for path in [paths.glossary_csv, paths.mappings_csv, paths.bde_csv]
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(
            "Required pipeline files are missing. Run the transform stage first or point --output-dir to an existing transform output. Missing: "
            + ", ".join(missing)
        )


def parse_args(repo_root: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the LDD to OpenMetadata pipeline")
    parser.add_argument(
        "--stages",
        default="all",
        help="Comma-separated list of stages: transform,import-glossary,preflight-mappings,apply-mappings,report or all",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan API changes without writing them")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Keep processing after per-item API failures",
    )
    parser.add_argument(
        "--endpoint",
        default="https://openmetadata.jac.dot:8585/api",
        help="OpenMetadata endpoint. Both http://host:port and http://host:port/api are accepted.",
    )
    parser.add_argument("--token", default="", help="Bearer token or personal access token")
    parser.add_argument(
        "--email",
        default=default_login_email(),
        help="OpenMetadata login email used when --token is not provided",
    )
    parser.add_argument(
        "--password",
        default=default_login_password(),
        help="OpenMetadata login password used when --token is not provided",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="HTTP timeout for OpenMetadata API calls",
    )
    parser.add_argument("--input", default="", help="Optional path to the source workbook")
    parser.add_argument(
        "--input-dir",
        default=str(repo_root / "dq-db" / "mock-data"),
        help="Directory scanned by the transform stage when --input is omitted",
    )
    parser.add_argument(
        "--output-dir",
        default=str(repo_root / "dq-db" / "mock-data" / "openmetadata-ready"),
        help="Directory containing the normalized CSV files and reports",
    )
    parser.add_argument(
        "--service-name",
        default="source_service",
        help="Service placeholder used during the transform stage",
    )
    parser.add_argument(
        "--database-name",
        default="source_database",
        help="Database placeholder used during the transform stage",
    )
    parser.add_argument(
        "--limit-terms",
        type=int,
        default=0,
        help="Optional limit for glossary term imports during testing",
    )
    parser.add_argument(
        "--limit-mappings",
        type=int,
        default=0,
        help="Optional limit for column mapping updates during testing",
    )
    parser.add_argument(
        "--min-mapping-coverage",
        type=float,
        default=0.05,
        help="Minimum required schema.table overlap ratio between mapping CSV and OpenMetadata catalog",
    )
    parser.add_argument(
        "--fail-on-low-coverage",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fail fast when preflight mapping coverage is below --min-mapping-coverage",
    )
    args = parser.parse_args()
    args.stage_list = parse_stages(args.stages)
    args.token = args.token or clean(os.environ.get("OM_TOKEN", ""))
    if not args.token:
        args.token = clean(os.environ.get("CATALOG_API_KEY", ""))
    return args


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    args = parse_args(repo_root)

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = resolve_paths(output_dir)

    state = load_existing_state(paths)
    transform_result: Optional[Dict[str, Any]] = None

    if "transform" in args.stage_list:
        transform_result = run_transform_stage(args, repo_root)

    if any(
        stage in args.stage_list
        for stage in ["import-glossary", "preflight-mappings", "apply-mappings", "report"]
    ):
        ensure_required_outputs(paths)

    client: Optional[OpenMetadataClient] = None
    catalog_tables: Sequence[Dict[str, Any]] = []
    if any(stage in args.stage_list for stage in ["import-glossary", "preflight-mappings", "apply-mappings"]):
        log_progress(
            f"[runner] connecting to OpenMetadata at {args.endpoint} for stages: {', '.join(args.stage_list)}"
        )
        client = OpenMetadataClient(
            endpoint=args.endpoint,
            timeout_seconds=args.timeout_seconds,
            token=args.token,
            email=args.email,
            password=args.password,
        )
        if not client.is_healthy():
            raise RuntimeError(f"OpenMetadata is not healthy at {args.endpoint}")
        log_progress("[runner] OpenMetadata health check succeeded")
        catalog_tables = client.list_tables(fields="", limit=100)
        log_progress(f"[runner] cached {len(catalog_tables)} catalog tables for reconciliation")

    glossary_rows = read_csv_rows(paths.glossary_csv) if paths.glossary_csv.exists() else []
    raw_mapping_rows = read_csv_rows(paths.mappings_csv) if paths.mappings_csv.exists() else []
    mapping_rows = list(raw_mapping_rows)

    if client is not None:
        mapping_rows = align_mapping_rows_to_catalog(raw_mapping_rows, catalog_tables, state=state)

    import_result = state.get("glossary_import", {})
    if "import-glossary" in args.stage_list:
        if client is None:
            raise RuntimeError("OpenMetadata client was not initialized")
        log_progress("[runner] stage import-glossary")
        import_result = import_glossary_stage(
            client,
            glossary_rows,
            dry_run=args.dry_run,
            continue_on_error=args.continue_on_error,
            state=state,
            limit_terms=args.limit_terms,
        )
        write_state(paths, state)

    if "preflight-mappings" in args.stage_list or "apply-mappings" in args.stage_list:
        if client is None:
            raise RuntimeError("OpenMetadata client was not initialized")
        log_progress("[runner] stage preflight-mappings")
        try:
            mapping_preflight_stage(
                mapping_rows=mapping_rows,
                catalog_tables=catalog_tables,
                state=state,
                min_mapping_coverage=args.min_mapping_coverage,
                fail_on_low_coverage=args.fail_on_low_coverage,
            )
        finally:
            # Persist preflight metrics even when the gate fails fast.
            write_state(paths, state)

    if "apply-mappings" in args.stage_list:
        if client is None:
            raise RuntimeError("OpenMetadata client was not initialized")
        log_progress("[runner] stage apply-mappings")
        apply_mappings_stage(
            client,
            glossary_rows=glossary_rows,
            mapping_rows=mapping_rows,
            import_result=import_result,
            dry_run=args.dry_run,
            continue_on_error=args.continue_on_error,
            limit_mappings=args.limit_mappings,
            state=state,
        )
        write_state(paths, state)

    report = build_report(
        stages=args.stage_list,
        paths=paths,
        state=state,
        transform_result=transform_result,
    )
    if "report" in args.stage_list or any(stage in args.stage_list for stage in ["import-glossary", "apply-mappings"]):
        log_progress("[runner] stage report")
        write_report(paths, report)

    print_report_summary(report, paths)


if __name__ == "__main__":
    main()
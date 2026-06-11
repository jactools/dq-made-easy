#!/usr/bin/env python3
"""
Generate per-tag OpenAPI Specification (OAS 3.x) JSON files from the FastAPI app.

Usage (inside the API container):
    python3 /app/scripts/generate_oas_per_tag.py /tmp/openapi_out

Each tag defined across all routers produces one <tag>.json file.
An index.json listing all generated specs is also written.
All components are included in every per-tag file to avoid broken $ref chains.

Implementation note:
    This script imports app.main dynamically after runtime sys.path patching so
    it can run from both the API container layout (/app) and the local repo
    layout without editor import-resolution issues.
"""
import json
import importlib
import os
import sys
from pathlib import Path

# Ensure imports resolve in both environments:
# - container: /app
# - local repo: <repo>/dq-api/fastapi
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
FASTAPI_ROOT = REPO_ROOT / "dq-api" / "fastapi"

if Path("/app/app").exists():
    sys.path.insert(0, "/app")
elif (FASTAPI_ROOT / "app").exists():
    sys.path.insert(0, str(FASTAPI_ROOT))
else:
    # Last resort: current working directory (useful for ad-hoc invocation)
    sys.path.insert(0, str(Path.cwd()))

# Provide minimal env so Settings validation passes without a live DB
os.environ.setdefault("REQUIRE_DATABASE", "false")
os.environ.setdefault("APP_NAME", "DQ API")

# Import after sys.path patching so this works in both local and container runs.
create_app = importlib.import_module("app.main").create_app  # pyright: ignore[reportMissingImports]

output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/openapi_out")
output_dir.mkdir(parents=True, exist_ok=True)

app = create_app()
schema: dict = app.openapi()

base_info = schema.get("info", {})
base_version = app.version

# ── Collect all tags that appear on at least one operation ──────────────────
all_tags: set[str] = set()
for path_item in schema.get("paths", {}).values():
    for operation in path_item.values():
        if isinstance(operation, dict):
            for tag in operation.get("tags", []):
                all_tags.add(tag)

generated: list[dict] = []

for tag in sorted(all_tags):
    # Filter paths: keep only paths where ≥1 operation carries this tag.
    # Within those path items, keep all methods (including those without the
    # tag) so shared parameters / schemas on the path object stay intact.
    filtered_paths: dict = {}
    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if isinstance(operation, dict) and tag in operation.get("tags", []):
                filtered_paths[path] = path_item
                break

    tag_spec: dict = {
        "openapi": schema.get("openapi", "3.1.0"),
        "info": {
            **base_info,
            "title": f"{base_info.get('title', 'DQ API')} — {tag}",
            "x-category": tag,
        },
        "paths": filtered_paths,
    }

    # Keep all servers / security schemes if present
    for key in ("servers", "components", "security", "tags", "externalDocs"):
        if key in schema:
            tag_spec[key] = schema[key]

    filename = f"{tag}.json"
    out_path = output_dir / filename
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(tag_spec, fh, indent=2)

    generated.append({
        "tag": tag,
        "file": filename,
        "url": f"/openapi/{filename}",
        "pathCount": len(filtered_paths),
    })
    print(f"  {filename:30s}  ({len(filtered_paths)} paths)", file=sys.stderr)

# ── Write index.json ─────────────────────────────────────────────────────────
index = {
    "openapi": schema.get("openapi", "3.1.0"),
    "apiVersion": base_version,
    "generatedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "specs": generated,
}
with open(output_dir / "index.json", "w", encoding="utf-8") as fh:
    json.dump(index, fh, indent=2)

print(
    f"\nGenerated {len(generated)} spec files + index.json → {output_dir}",
    file=sys.stderr,
)

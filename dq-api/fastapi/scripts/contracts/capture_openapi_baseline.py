import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[4]
DQ_UTILS_SRC = REPO_ROOT / "dq-utils" / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if DQ_UTILS_SRC.exists() and str(DQ_UTILS_SRC) not in sys.path:
    sys.path.insert(0, str(DQ_UTILS_SRC))


def _prepare_fastapi_contract_env() -> None:
    os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")
    os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "")


def _load_from_url(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=30) as response:
        payload = response.read().decode("utf-8")
        return json.loads(payload)


def _load_from_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _load_from_fastapi_app() -> dict[str, Any]:
    _prepare_fastapi_contract_env()
    from app.main import app

    return app.openapi()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture OpenAPI contract baseline for API-6.2 parity checks."
    )
    parser.add_argument(
        "--source",
        choices=["url", "file", "fastapi"],
        default="fastapi",
        help="Source for baseline capture.",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:4001/v1/openapi.json",
        help="OpenAPI URL when --source url.",
    )
    parser.add_argument(
        "--file",
        default="contracts/current/openapi.json",
        help="OpenAPI JSON file when --source file.",
    )
    parser.add_argument(
        "--output",
        default="contracts/baseline/openapi-legacy-v1.json",
        help="Output baseline path.",
    )
    args = parser.parse_args()

    if args.source == "url":
        spec = _load_from_url(args.url)
    elif args.source == "file":
        spec = _load_from_file(Path(args.file))
    else:
        spec = _load_from_fastapi_app()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")

    print(f"Captured baseline to: {output_path}")
    print(f"OpenAPI title: {spec.get('info', {}).get('title', 'unknown')}")
    print(f"Path count: {len(spec.get('paths', {}))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
import ssl
from pathlib import Path
from urllib import parse


def resolve_ca_bundle(repo_root: Path) -> Path:
    bundle_override = os.getenv("OPENMETADATA_CA_BUNDLE", "").strip()
    candidates = []
    if bundle_override:
        candidates.append(Path(bundle_override).expanduser())
    candidates.append(repo_root / "tmp" / "certs" / "mkcert-rootCA.pem")

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        "OpenMetadata HTTPS requires a CA bundle. Run scripts/create_certs.sh "
        "or set OPENMETADATA_CA_BUNDLE to a valid root CA PEM file."
    )


def build_ssl_context(endpoint: str, repo_root: Path) -> ssl.SSLContext | None:
    if parse.urlparse(endpoint).scheme != "https":
        return None

    ca_bundle = resolve_ca_bundle(repo_root)
    return ssl.create_default_context(cafile=str(ca_bundle))
import os
import subprocess
from pathlib import Path


def test_wait_for_keycloak_ready_uses_cacert_when_configured(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    curl_bin = tmp_path / "curl"
    curl_bin.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" > \"$TEST_OUTPUT\"\n"
        "exit 0\n"
    )
    curl_bin.chmod(0o755)

    ca_bundle = tmp_path / "ca.pem"
    ca_bundle.write_text("dummyca")

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    env["CURL_CA_BUNDLE"] = str(ca_bundle)
    env["TEST_OUTPUT"] = str(tmp_path / "curl-args.txt")
    env["KEYCLOAK_READINESS_MAX_ATTEMPTS"] = "1"
    env["KEYCLOAK_READINESS_SLEEP_SECONDS"] = "0"

    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            "source scripts/supporting/keycloak_readiness.sh; wait_for_keycloak_ready https://example.test/realms/demo/.well-known/openid-configuration Keycloak",
        ],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr

    curl_args = (tmp_path / "curl-args.txt").read_text()
    assert "--cacert" in curl_args
    assert str(ca_bundle) in curl_args

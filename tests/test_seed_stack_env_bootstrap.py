import os
import subprocess
from pathlib import Path


def test_source_runtime_env_dependencies_primes_root_env_before_sourcing(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    temp_root = tmp_path / "repo"
    (temp_root / "tmp").mkdir(parents=True)
    (temp_root / "scripts" / "supporting").mkdir(parents=True)

    (temp_root / ".env.dev.local").write_text(
        "COMPOSED_VALUE=${KEYCLOAK_JACCLOUD_PASSWORD}-${OPERATOR_LOGIN_PASSWORD}\n",
        encoding="utf-8",
    )
    (temp_root / "tmp" / "secrets.dev.env").write_text(
        "KEYCLOAK_JACCLOUD_PASSWORD=from-secrets\n",
        encoding="utf-8",
    )
    (temp_root / "tmp" / "keycloak_seed_user_credentials.dev.env").write_text(
        "OPERATOR_LOGIN_PASSWORD=from-credentials\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["ROOT_DIR"] = str(temp_root)

    result = subprocess.run(
        [
            "/bin/bash",
            "-lc",
            (
                "set -euo pipefail; "
                f"source {repo_root}/scripts/supporting/root_env_file.sh; "
                "source_runtime_env_dependencies \"$ROOT_DIR/.env.dev.local\"; "
                "set -a; source \"$ROOT_DIR/.env.dev.local\"; set +a; "
                'printf "%s\\n" "$COMPOSED_VALUE"'
            ),
        ],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "from-secrets-from-credentials"

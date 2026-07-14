import os
import subprocess
from pathlib import Path


def test_source_selected_root_env_file_keeps_generated_secrets_after_root_env(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    temp_root = tmp_path / "repo"
    (temp_root / "tmp").mkdir(parents=True)
    (temp_root / "scripts" / "supporting").mkdir(parents=True)

    (temp_root / ".env.dev.local").write_text(
        "COMPOSED_VALUE=${KEYCLOAK_JACCLOUD_PASSWORD}-${OPERATOR_LOGIN_PASSWORD}\n"
        "KEYCLOAK_JACCLOUD_PASSWORD=from-root\n",
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
                "ROOT_ENV_FILE=\"$ROOT_DIR/.env.dev.local\"; "
                "source_selected_root_env_file; "
                'printf "%s\\n%s\\n" "$COMPOSED_VALUE" "$KEYCLOAK_JACCLOUD_PASSWORD"'
            ),
        ],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["from-secrets-from-credentials", "from-secrets"]

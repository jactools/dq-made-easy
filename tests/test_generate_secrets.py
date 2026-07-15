import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_RUNNER = REPO_ROOT / "scripts" / "python_arm64.sh"


def test_generate_secrets_force_regenerates_keycloak_admin_password(tmp_path):
    secrets_file = REPO_ROOT / "tmp" / "secrets.dev.env"
    backup_path = tmp_path / "secrets.dev.env.bak"
    original_content = secrets_file.read_text(encoding="utf-8") if secrets_file.exists() else None

    if original_content is not None:
        backup_path.write_text(original_content, encoding="utf-8")

    try:
        secrets_file.parent.mkdir(parents=True, exist_ok=True)
        secrets_file.write_text('# existing secrets\nKEYCLOAK_ADMIN_PASS="preserved-password"\n', encoding="utf-8")

        env = os.environ.copy()
        env["PATH"] = os.environ.get("PATH", "")
        completed = subprocess.run(
            [
                str(PYTHON_RUNNER),
                "--python-bin",
                str(REPO_ROOT / "venv" / "bin" / "python"),
                "-c",
                "print('ok')",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr or completed.stdout

        subprocess.run(
            [
                "bash",
                str(REPO_ROOT / "scripts" / "generate_secrets.sh"),
                "--env-file",
                str(REPO_ROOT / ".env.dev.local"),
                "--force",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        generated = secrets_file.read_text(encoding="utf-8")
        assert 'KEYCLOAK_ADMIN_PASS="preserved-password"' not in generated
        assert 'KEYCLOAK_SYSTEM_ADMIN_PASSWORD="preserved-password"' not in generated

        keycloak_admin_pass = None
        keycloak_system_admin_password = None
        for line in generated.splitlines():
            if line.startswith('KEYCLOAK_ADMIN_PASS='):
                keycloak_admin_pass = line.split('=', 1)[1].strip().strip('"')
            if line.startswith('KEYCLOAK_SYSTEM_ADMIN_PASSWORD='):
                keycloak_system_admin_password = line.split('=', 1)[1].strip().strip('"')

        assert keycloak_admin_pass
        assert keycloak_system_admin_password
        assert keycloak_admin_pass == keycloak_system_admin_password
        assert keycloak_admin_pass != 'preserved-password'
    finally:
        if original_content is None:
            if secrets_file.exists():
                secrets_file.unlink()
        else:
            secrets_file.write_text(original_content, encoding="utf-8")

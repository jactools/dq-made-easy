ROOT_DIR=$(dirname "$(dirname "$(realpath "$0")")")
cd "$ROOT_DIR"

PYTHON_RUNNER="$ROOT_DIR/scripts/python_arm64.sh"

source .venv/bin/activate
"$PYTHON_RUNNER" --python-bin .venv/bin/python -m pip install --upgrade pip setuptools wheel
"$PYTHON_RUNNER" --python-bin .venv/bin/python -m pip install cryptography

KEY=$("$PYTHON_RUNNER" --python-bin .venv/bin/python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
)

echo "$KEY"

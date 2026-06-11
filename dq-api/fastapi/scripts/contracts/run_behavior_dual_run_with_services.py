import argparse
import os
import platform
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

FASTAPI_ROOT = Path(__file__).resolve().parents[2]
DQ_API_ROOT = Path(__file__).resolve().parents[3]
DUAL_RUN_SCRIPT = FASTAPI_ROOT / "scripts" / "contracts" / "run_behavior_dual_run.py"
WORKSPACE_VENV_PYTHON = DQ_API_ROOT.parent / "venv" / "bin" / "python"


def _wait_for_health(url: str, timeout_seconds: float, poll_interval_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2.0) as response:
                if int(response.status) < 500:
                    return True
        except HTTPError as error:
            if int(error.code) < 500:
                return True
        except URLError:
            pass
        except TimeoutError:
            pass
        time.sleep(poll_interval_seconds)
    return False


def _terminate_process(process: subprocess.Popen[bytes], name: str) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    print(f"Stopped {name}")


def _split_command(raw: str) -> list[str]:
    parts = shlex.split(raw)
    if not parts:
        raise ValueError("Command cannot be empty")
    return parts


def _resolve_python_for_runtime() -> str:
    if WORKSPACE_VENV_PYTHON.exists():
        return str(WORKSPACE_VENV_PYTHON)
    return sys.executable


def _host_supports_arm64() -> bool:
    if platform.system().lower() != "darwin":
        return False
    try:
        completed = subprocess.run(
            ["sysctl", "-in", "hw.optional.arm64"],
            check=False,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip() == "1"
    except (FileNotFoundError, OSError):
        return False


def _resolve_python_invocation(python_executable: str, python_arch: str) -> list[str]:
    should_force_arm64 = python_arch == "arm64" or (
        python_arch == "auto" and _host_supports_arm64()
    )
    if should_force_arm64 and shutil.which("arch"):
        return ["arch", "-arm64", python_executable]
    return [python_executable]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run API-6.9 dual-run behavior diff by managing both legacy and FastAPI services"
    )
    parser.add_argument(
        "--legacy-command",
        default="",
        help="Command used to start legacy API (optional; required only for historical dual-run replays)",
    )
    runtime_python = _resolve_python_for_runtime()

    parser.add_argument(
        "--fastapi-command",
        default=f"{runtime_python} -m uvicorn app.main:app --host 127.0.0.1 --port 4010",
        help="Command used to start FastAPI API (run in dq-api/fastapi root)",
    )
    parser.add_argument("--legacy-port", type=int, default=4001)
    parser.add_argument("--fastapi-port", type=int, default=4010)
    parser.add_argument(
        "--scenarios",
        default="contracts/verification/api69-dual-run-smoke.json",
        help="Scenario file path relative to fastapi root",
    )
    parser.add_argument(
        "--output",
        default="contracts/current/api69-behavior-diff-report.json",
        help="JSON report output path relative to fastapi root",
    )
    parser.add_argument(
        "--markdown-output",
        default="contracts/current/api69-behavior-diff-report.md",
        help="Markdown report output path relative to fastapi root",
    )
    parser.add_argument(
        "--startup-timeout-seconds",
        type=float,
        default=60.0,
        help="Maximum time to wait for each service to become healthy",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=1.0,
        help="Health-check poll interval",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=10.0,
        help="Per-request timeout passed to dual-run script",
    )
    parser.add_argument(
        "--python-arch",
        choices=["auto", "native", "arm64"],
        default="auto",
        help="Python architecture mode used for managed FastAPI and dual-run commands",
    )
    parser.add_argument(
        "--logs-dir",
        default="contracts/current",
        help="Directory for service logs relative to fastapi root",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved commands and exit without starting services",
    )
    args = parser.parse_args()

    if not args.legacy_command.strip():
        parser.error(
            "--legacy-command is required for dual-run replay. API-6.11 decommissioned the legacy API runtime."
        )

    runtime_python_cmd = _resolve_python_invocation(runtime_python, args.python_arch)

    if args.fastapi_command == f"{runtime_python} -m uvicorn app.main:app --host 127.0.0.1 --port 4010":
        args.fastapi_command = " ".join(
            [
                *runtime_python_cmd,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.fastapi_port),
            ]
        )

    legacy_command = _split_command(args.legacy_command)
    fastapi_command = _split_command(args.fastapi_command)
    scenario_path = FASTAPI_ROOT / args.scenarios
    if not scenario_path.exists():
        print(f"ERROR: scenario file not found: {scenario_path}")
        return 2

    logs_dir = FASTAPI_ROOT / args.logs_dir
    legacy_log_path = logs_dir / "api69-legacy.log"
    fastapi_log_path = logs_dir / "api69-fastapi.log"

    legacy_base_url = f"http://127.0.0.1:{args.legacy_port}"
    fastapi_base_url = f"http://127.0.0.1:{args.fastapi_port}"
    legacy_health_url = f"{legacy_base_url}/v1/health"
    fastapi_health_url = f"{fastapi_base_url}/api/system/v1/health"

    if args.dry_run:
        print(f"Legacy command: {' '.join(legacy_command)}")
        print(f"FastAPI command: {' '.join(fastapi_command)}")
        print(f"Legacy health URL: {legacy_health_url}")
        print(f"FastAPI health URL: {fastapi_health_url}")
        print(f"Scenarios: {scenario_path}")
        return 0

    logs_dir.mkdir(parents=True, exist_ok=True)

    legacy_log = legacy_log_path.open("wb")
    fastapi_log = fastapi_log_path.open("wb")
    legacy_process: subprocess.Popen[bytes] | None = None
    fastapi_process: subprocess.Popen[bytes] | None = None

    try:
        legacy_env = os.environ.copy()
        legacy_env["PORT"] = str(args.legacy_port)
        legacy_process = subprocess.Popen(
            legacy_command,
            cwd=DQ_API_ROOT,
            stdout=legacy_log,
            stderr=subprocess.STDOUT,
            env=legacy_env,
        )
        print(f"Started legacy API (pid={legacy_process.pid}), log={legacy_log_path}")

        fastapi_env = os.environ.copy()
        fastapi_env["PORT"] = str(args.fastapi_port)
        fastapi_process = subprocess.Popen(
            fastapi_command,
            cwd=FASTAPI_ROOT,
            stdout=fastapi_log,
            stderr=subprocess.STDOUT,
            env=fastapi_env,
        )
        print(f"Started FastAPI (pid={fastapi_process.pid}), log={fastapi_log_path}")

        if not _wait_for_health(legacy_health_url, args.startup_timeout_seconds, args.poll_interval_seconds):
            print(f"ERROR: legacy API did not become healthy: {legacy_health_url}")
            return 1
        print("Legacy API is healthy")

        if not _wait_for_health(fastapi_health_url, args.startup_timeout_seconds, args.poll_interval_seconds):
            print(f"ERROR: FastAPI did not become healthy: {fastapi_health_url}")
            return 1
        print("FastAPI is healthy")

        if legacy_process.poll() is not None:
            print("ERROR: legacy API exited before dual-run started")
            return 1
        if fastapi_process.poll() is not None:
            print("ERROR: FastAPI exited before dual-run started")
            return 1

        dual_run_command = [
            *runtime_python_cmd,
            str(DUAL_RUN_SCRIPT),
            "--legacy-base-url",
            legacy_base_url,
            "--fastapi-base-url",
            fastapi_base_url,
            "--scenarios",
            str(args.scenarios),
            "--output",
            str(args.output),
            "--markdown-output",
            str(args.markdown_output),
            "--timeout-seconds",
            str(args.request_timeout_seconds),
        ]

        completed = subprocess.run(dual_run_command, cwd=FASTAPI_ROOT)
        return completed.returncode
    finally:
        if legacy_process is not None:
            _terminate_process(legacy_process, "legacy API")
        if fastapi_process is not None:
            _terminate_process(fastapi_process, "FastAPI")
        legacy_log.close()
        fastapi_log.close()


if __name__ == "__main__":
    raise SystemExit(main())

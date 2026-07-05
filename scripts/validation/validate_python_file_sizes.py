#!/usr/bin/env python3
"""
validate_python_file_sizes.py — Enforce the 1000-line rule for Python files.

What it does:
  - Scans all tracked Python files (excluding build/, venv/, __pycache__, node_modules).
  - Enforces that any new/created/generated file must have fewer than 1000 lines.
  - Summarizes existing files that already exceed 1000 lines (unchanged or modified).
  - Reports extreme values (largest files by line count).
  - Exits non-zero when new files violate the threshold.

Usage:
  python scripts/validation/validate_python_file_sizes.py [OPTIONS]

Options:
  --threshold N        Line count threshold (default: 1000)
  --new-only           Only check new/created files (not existing ones)
  --extreme N          Show top N extreme values (default: 10)
  --json               Output summary in JSON format to stdout
  --quiet              Suppress verbose output
  --allow-list FILE    Path to allow-list file (one relative path per line)
  -h, --help           Show this help message

# validate: groups=repo
# validate: include=false
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class FileInfo:
    path: str
    lines: int
    is_new: bool
    exceeds_threshold: bool = False


@dataclass
class ValidationSummary:
    total_files: int = 0
    total_lines: int = 0
    files_over_threshold: list[FileInfo] = field(default_factory=list)
    new_file_violations: list[FileInfo] = field(default_factory=list)
    extreme_values: list[FileInfo] = field(default_factory=list)
    extreme_count: int = 10
    threshold: int = 1000


EXCLUDE_DIRS = {
    "build",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".tox",
    ".eggs",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Python file sizes against the 1000-line rule.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=1000,
        help="Maximum allowed lines per Python file (default: 1000)",
    )
    parser.add_argument(
        "--new-only",
        action="store_true",
        help="Only check new/created files, skip existing file report",
    )
    parser.add_argument(
        "--extreme",
        type=int,
        default=10,
        help="Number of extreme values to show (default: 10)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output summary in JSON format",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose output",
    )
    parser.add_argument(
        "--allow-list",
        type=Path,
        default=None,
        help="Path to allow-list file (one relative path per line)",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        metavar="PATH",
        help="Check only these files (used by pre-commit hook with pass_filenames)",
    )
    return parser.parse_args(argv)


def is_excluded(path: Path) -> bool:
    """Return True if the path falls under an excluded directory."""
    parts = path.parts
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True
    return False


def count_lines(path: Path) -> int:
    """Count non-empty lines in a file."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return sum(1 for line in fh if line.strip())
    except (OSError, PermissionError):
        return 0


def get_tracked_files(root: Path) -> list[Path]:
    """Get all git-tracked Python files."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", "*.py"],
            capture_output=True,
            text=True,
            cwd=str(root),
            check=True,
        )
        files = [root / p for p in result.stdout.strip().split("\n") if p]
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback: scan all Python files if git is unavailable
        files = sorted(root.rglob("*.py"))
    return [f for f in files if not is_excluded(f)]


def get_new_files(root: Path) -> set[str]:
    """Get set of new (untracked) Python files."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "--", "*.py"],
            capture_output=True,
            text=True,
            cwd=str(root),
            check=True,
        )
        return {p.strip() for p in result.stdout.strip().split("\n") if p.strip()}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return set()


def load_allow_list(path: Path) -> set[str]:
    """Load allow-list of files that are exempt from the threshold check."""
    if not path or not path.exists():
        return set()
    entries: set[str] = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#")[0].strip()  # Strip inline comments
            if line:
                entries.add(line)
    return entries


def validate_staged(
    root: Path,
    staged_paths: list[Path],
    threshold: int,
    allow_list: set[str],
    new_files: set[str],
    args: argparse.Namespace,
) -> tuple[ValidationSummary, bool]:
    """Validate only the given files (used by pre-commit hook)."""
    summary = ValidationSummary(threshold=threshold, extreme_count=args.extreme)
    all_files: list[FileInfo] = []

    for fpath in staged_paths:
        # Resolve relative to repo root
        try:
            rel_path = fpath.relative_to(root)
            rel = str(rel_path)
        except ValueError:
            rel = str(fpath)

        lines = count_lines(fpath)
        is_new = rel in new_files
        is_exempt = rel in allow_list
        info = FileInfo(
            path=rel,
            lines=lines,
            is_new=is_new,
            exceeds_threshold=lines >= threshold and not is_exempt,
        )
        all_files.append(info)
        summary.total_files += 1
        summary.total_lines += lines

        if info.exceeds_threshold:
            summary.files_over_threshold.append(info)
        if is_new and info.exceeds_threshold:
            summary.new_file_violations.append(info)

    all_files.sort(key=lambda f: f.lines, reverse=True)
    summary.extreme_values = all_files[:args.extreme]
    has_violations = len(summary.new_file_violations) > 0
    return summary, has_violations


def validate(root: Path, args: argparse.Namespace) -> tuple[ValidationSummary, bool]:
    """Run the validation and return (summary, has_violations)."""
    threshold = args.threshold
    allow_list = load_allow_list(args.allow_list) if args.allow_list else set()
    new_files = get_new_files(root)

    # If --files provided (pre-commit), only check those files
    if args.files:
        staged_paths = [Path(f) for f in args.files if f.endswith(".py") and not is_excluded(Path(f))]
        return validate_staged(root, staged_paths, threshold, allow_list, new_files, args)

    tracked_files = get_tracked_files(root)

    summary = ValidationSummary(
        threshold=threshold,
        extreme_count=args.extreme,
    )

    all_files: list[FileInfo] = []

    for fpath in tracked_files:
        rel = str(fpath.relative_to(root))
        lines = count_lines(fpath)
        is_new = rel in new_files
        info = FileInfo(
            path=rel,
            lines=lines,
            is_new=is_new,
            exceeds_threshold=lines >= threshold and rel not in allow_list,
        )
        all_files.append(info)
        summary.total_files += 1
        summary.total_lines += lines

        if info.exceeds_threshold:
            summary.files_over_threshold.append(info)

        if is_new and info.exceeds_threshold:
            summary.new_file_violations.append(info)

    # Also check untracked new files that may not appear in ls-files
    for new_rel in new_files:
        new_path = root / new_rel
        if new_path.exists() and not is_excluded(new_path):
            # Check if already processed (in tracked files)
            if not any(f.path == new_rel for f in all_files):
                lines = count_lines(new_path)
                is_exempt = new_rel in allow_list
                info = FileInfo(
                    path=new_rel,
                    lines=lines,
                    is_new=True,
                    exceeds_threshold=lines >= threshold and not is_exempt,
                )
                all_files.append(info)
                summary.total_files += 1
                summary.total_lines += lines
                if info.exceeds_threshold:
                    summary.files_over_threshold.append(info)
                    summary.new_file_violations.append(info)

    # Extreme values (sorted by line count descending)
    all_files.sort(key=lambda f: f.lines, reverse=True)
    summary.extreme_values = all_files[: args.extreme]

    has_violations = len(summary.new_file_violations) > 0
    return summary, has_violations


def print_report(summary: ValidationSummary, args: argparse.Namespace) -> None:
    """Print the validation report to stdout."""
    quiet = args.quiet

    if not quiet:
        print("=" * 72)
        print("Python File Size Validation Report")
        print("=" * 72)

        print(f"\nRepository scan: {summary.total_files} Python files, {summary.total_lines} total lines")
        print(f"Threshold: {summary.threshold} lines\n")

    # New file violations (these are errors)
    if summary.new_file_violations:
        print("-" * 72)
        print(f"NEW FILE VIOLATIONS ({len(summary.new_file_violations)} files exceed {summary.threshold} lines)")
        print("-" * 72)
        for f in summary.new_file_violations:
            print(f"  FAIL  {f.path}: {f.lines} lines")
        print()

    # Existing files over threshold (informational)
    existing_violations = [f for f in summary.files_over_threshold if not f.is_new]
    if existing_violations and not args.new_only:
        print("-" * 72)
        print(f"EXISTING FILES OVER THRESHOLD ({len(existing_violations)} files — informational)")
        print("-" * 72)
        for f in existing_violations[:50]:  # Cap display
            print(f"  WARN  {f.path}: {f.lines} lines")
        if len(existing_violations) > 50:
            print(f"  ... and {len(existing_violations) - 50} more (use --extreme to see all)")
        print()

    # Extreme values
    if summary.extreme_values and not quiet:
        print("-" * 72)
        print(f"TOP {len(summary.extreme_values)} LARGEST FILES")
        print("-" * 72)
        for i, f in enumerate(summary.extreme_values, 1):
            flag = " NEW" if f.is_new else ""
            flag += " [OVER]" if f.exceeds_threshold else ""
            print(f"  {i:3d}. {f.path}: {f.lines} lines{flag}")
        print()

    # Summary
    if not quiet:
        print("=" * 72)
        print("Summary:")
        print(f"  Total files scanned:    {summary.total_files}")
        print(f"  Total lines of code:    {summary.total_lines}")
        print(f"  Files over threshold:   {len(summary.files_over_threshold)}")
        print(f"  New file violations:    {len(summary.new_file_violations)}")
        if summary.extreme_values:
            print(f"  Largest file:             {summary.extreme_values[0].path} ({summary.extreme_values[0].lines} lines)")
        print("=" * 72)


def print_json(summary: ValidationSummary) -> None:
    """Output summary as JSON."""
    data: dict[str, Any] = {
        "total_files": summary.total_files,
        "total_lines": summary.total_lines,
        "threshold": summary.threshold,
        "files_over_threshold": [
            {"path": f.path, "lines": f.lines, "is_new": f.is_new}
            for f in summary.files_over_threshold
        ],
        "new_file_violations": [
            {"path": f.path, "lines": f.lines}
            for f in summary.new_file_violations
        ],
        "extreme_values": [
            {"rank": i, "path": f.path, "lines": f.lines, "is_new": f.is_new}
            for i, f in enumerate(summary.extreme_values, 1)
        ],
    }
    print(json.dumps(data, indent=2))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[2]

    summary, has_violations = validate(root, args)

    if args.json_output:
        print_json(summary)
    else:
        print_report(summary, args)

    if has_violations:
        print(f"\nERROR: {len(summary.new_file_violations)} new file(s) exceed the {summary.threshold}-line threshold.", file=sys.stderr)
        print("New/created Python files must be under 1000 lines. Refactor into smaller modules.", file=sys.stderr)
        return 1

    if summary.files_over_threshold and not args.quiet:
        print(f"\nINFO: {len(summary.files_over_threshold)} existing file(s) exceed {summary.threshold} lines.", file=sys.stderr)
        print("(These are informational — new files must still be under the threshold.)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

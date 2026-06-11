#!/usr/bin/env python3
"""Sync actionable markdown backlog sections into GitHub Project v2 draft items.

The script scans markdown files in the repository, finds backlog-like sections
such as TODO, Next Steps, Open Items, and Known Gaps, and creates draft issues
inside the configured GitHub Project.

Use the shell wrapper at scripts/sync_markdown_backlog_to_github_project.sh so
the repository's arm64 Python runner is always used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ACTIONABLE_HEADING_RE = re.compile(
    r"(" 
    r"todo|next steps?|open items?|known gaps?|action items?|backlog|"
    r"stored to-do|known limitations?|future enhancements?|missing steps?|"
    r"proposed requirements?"
    r")",
    re.IGNORECASE,
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(?P<text>.+?)\s*$")
CHECKBOX_RE = re.compile(r"^\s*[-*+]\s+\[[ xX]\]\s+(?P<text>.+?)\s*$")
BULLET_RE = re.compile(r"^\s*[-*+]\s+(?P<text>.+?)\s*$")
NUMBERED_RE = re.compile(r"^\s*\d+\.\s+(?P<text>.+?)\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
MARKDOWN_SUFFIXES = (".md", ".markdown")
BACKLOG_ROOT_PREFIXES = (
    "docs/status/",
    "docs/implementation-details/",
    "docs/fixes/",
)
BACKLOG_NAME_RE = re.compile(
    r"(" 
    r"TODO|PLAN|MILESTONE|SETUP|QUICKSTART|SUMMARY|FIX|TEST|"
    r"IMPLEMENTATION_PHASE_1|BASELINE"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Heading:
    line_index: int
    level: int
    text: str


@dataclass(frozen=True)
class BacklogItem:
    title: str
    body: str
    sync_key: str


def run_gh_json(args: list[str]) -> object:
    completed = subprocess.run(
        ["gh", *args],
        check=True,
        text=True,
        capture_output=True,
    )
    output = completed.stdout.strip()
    return json.loads(output) if output else {}


def run_gh_text(args: list[str]) -> str:
    completed = subprocess.run(
        ["gh", *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_state(state_path: Path) -> set[str]:
    if not state_path.exists():
        return set()

    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return set()

    keys = data.get("synced_keys", []) if isinstance(data, dict) else []
    return {str(key) for key in keys}


def save_state(state_path: Path, keys: set[str]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"synced_keys": sorted(keys)}
    state_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def strip_markdown(text: str) -> str:
    cleaned = re.sub(r"`([^`]+)`", r"\1", text)
    cleaned = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" -:;.,")


def truncate(text: str, limit: int = 120) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def iter_markdown_files(root: Path) -> Iterable[Path]:
    excluded_parts = {".git", "node_modules", "dist", "tmp", "venv", ".venv", "coverage"}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in MARKDOWN_SUFFIXES:
            continue
        if any(part in excluded_parts for part in path.parts):
            continue
        yield path


def should_include_file(relative_path: Path, scope: str) -> bool:
    relative = relative_path.as_posix()
    if scope == "all":
        return True

    return any(relative.startswith(prefix) for prefix in BACKLOG_ROOT_PREFIXES) and bool(
        BACKLOG_NAME_RE.search(relative_path.name)
    )


def parse_headings(lines: list[str]) -> list[Heading]:
    headings: list[Heading] = []
    in_fence = False
    for index, line in enumerate(lines):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING_RE.match(line)
        if match:
            headings.append(
                Heading(
                    line_index=index,
                    level=len(match.group(1)),
                    text=match.group("text").strip(),
                )
            )
    return headings


def section_end(headings: list[Heading], current_index: int, section_level: int, lines_count: int) -> int:
    for next_heading in headings[current_index + 1 :]:
        if next_heading.level <= section_level:
            return next_heading.line_index
    return lines_count


def extract_actionable_lines(lines: list[str]) -> list[str]:
    items: list[str] = []
    in_fence = False
    for line in lines:
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        for pattern in (CHECKBOX_RE, BULLET_RE, NUMBERED_RE):
            match = pattern.match(line)
            if match:
                text = strip_markdown(match.group("text"))
                if text and not text.endswith(":"):
                    items.append(text)
                break
    return items


def section_excerpt(lines: list[str], max_lines: int = 18) -> str:
    excerpt_lines: list[str] = []
    for line in lines:
        if not line.strip() and not excerpt_lines:
            continue
        excerpt_lines.append(line.rstrip())
        if len(excerpt_lines) >= max_lines:
            break
    return "\n".join(excerpt_lines).strip()


def build_backlog_items(file_path: Path, root: Path) -> list[BacklogItem]:
    lines = file_path.read_text(encoding="utf-8").splitlines()
    headings = parse_headings(lines)
    items: list[BacklogItem] = []
    covered_until = -1

    for heading_index, heading in enumerate(headings):
        if heading.line_index < covered_until:
            continue
        if not ACTIONABLE_HEADING_RE.search(heading.text):
            continue

        end_line = section_end(headings, heading_index, heading.level, len(lines))
        covered_until = end_line
        section_lines = lines[heading.line_index + 1 : end_line]
        actionable_lines = extract_actionable_lines(section_lines)

        relative_path = file_path.relative_to(root).as_posix()
        heading_label = heading.text

        sync_key = hashlib.sha1(f"{relative_path}\n{heading_label}".encode("utf-8")).hexdigest()
        body = build_item_body(
            relative_path=relative_path,
            heading_label=heading_label,
            action_text=None,
            excerpt=section_excerpt(section_lines),
            actionable_lines=actionable_lines,
            sync_key=sync_key,
        )
        title = truncate(f"{file_path.stem}: {heading_label}", 120)
        items.append(BacklogItem(title=title, body=body, sync_key=sync_key))

    return items


def build_item_body(
    *,
    relative_path: str,
    heading_label: str,
    action_text: str | None,
    actionable_lines: list[str] | None = None,
    excerpt: str,
    sync_key: str,
) -> str:
    action_lines = actionable_lines or ([] if action_text is None else [action_text])
    if action_lines:
        action_block = "\n".join(f"- {line}" for line in action_lines)
    else:
        action_block = "- Section-level backlog item"
    body = [
        f"Source file: `{relative_path}`",
        f"Source heading: `{heading_label}`",
        "Action items:",
        action_block,
        "",
        "Excerpt:",
        "```markdown",
        excerpt or "(no excerpt available)",
        "```",
        "",
        f"<!-- md-project-sync-key: {sync_key} -->",
    ]
    return "\n".join(body).strip() + "\n"


def get_field_option_id(fields: list[dict[str, object]], field_name: str, option_name: str) -> tuple[str, str]:
    for field in fields:
        if field.get("name") != field_name:
            continue
        field_id = str(field["id"])
        for option in field.get("options", []):
            if option.get("name") == option_name:
                return field_id, str(option["id"])
        available = ", ".join(str(option.get("name")) for option in field.get("options", []))
        raise SystemExit(f"Project field '{field_name}' does not contain option '{option_name}'. Available: {available}")
    raise SystemExit(f"Project field '{field_name}' not found")


def create_draft_item(project_number: int, owner: str, title: str, body: str) -> str:
    return run_gh_text(
        [
            "project",
            "item-create",
            str(project_number),
            "--owner",
            owner,
            "--title",
            title,
            "--body",
            body,
            "--format",
            "json",
            "--jq",
            ".id",
        ]
    )


def set_single_select_field(project_id: str, item_id: str, field_id: str, option_id: str) -> None:
    subprocess.run(
        [
            "gh",
            "project",
            "item-edit",
            "--id",
            item_id,
            "--project-id",
            project_id,
            "--field-id",
            field_id,
            "--single-select-option-id",
            option_id,
        ],
        check=True,
        text=True,
        capture_output=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default="jactools", help="GitHub Project owner login")
    parser.add_argument("--project-number", type=int, default=1, help="GitHub Project number")
    parser.add_argument("--status", default="Backlog", help="Project Status field value")
    parser.add_argument("--priority", default="P2", help="Project Priority field value")
    parser.add_argument(
        "--scope",
        choices=("backlog", "all"),
        default="backlog",
        help="Which markdown set to scan; backlog keeps the run focused on actionable docs",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print items without creating them")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit on created items")
    parser.add_argument("--reset-state", action="store_true", help="Ignore the local sync cache")
    parser.add_argument(
        "--state-file",
        default="tmp/github-project-backlog-sync-state.json",
        help="Path to the local sync cache",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root()
    state_file = root / args.state_file

    project = run_gh_json(["project", "view", str(args.project_number), "--owner", args.owner, "--format", "json"])
    project_id = str(project.get("id", "")).strip()
    if not project_id:
        raise SystemExit("Unable to resolve target project id")

    fields = run_gh_json(["project", "field-list", str(args.project_number), "--owner", args.owner, "--format", "json"])
    field_items = list(fields.get("fields", [])) if isinstance(fields, dict) else []
    status_field_id, status_option_id = get_field_option_id(field_items, "Status", args.status)
    priority_field_id, priority_option_id = get_field_option_id(field_items, "Priority", args.priority)

    synced_keys = set() if args.reset_state else load_state(state_file)
    discovered_items: list[BacklogItem] = []

    for markdown_file in iter_markdown_files(root):
        if not should_include_file(markdown_file.relative_to(root), args.scope):
            continue
        discovered_items.extend(build_backlog_items(markdown_file, root))

    items_to_sync = [item for item in discovered_items if item.sync_key not in synced_keys]

    print(f"Discovered {len(discovered_items)} actionable backlog items.")
    print(f"Syncing {len(items_to_sync)} new items to project {args.owner}/{args.project_number}.")

    if args.dry_run:
        for item in items_to_sync:
            print(f"- {item.title}")
        return 0

    created = 0
    for item in items_to_sync:
        item_id = create_draft_item(args.project_number, args.owner, item.title, item.body)
        set_single_select_field(project_id, item_id, status_field_id, status_option_id)
        set_single_select_field(project_id, item_id, priority_field_id, priority_option_id)
        synced_keys.add(item.sync_key)
        created += 1
        print(f"Created project item: {item.title}")

    save_state(state_file, synced_keys)
    print(f"Done. Created {created} new project items.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Read-only CLI for inspecting Agent JSONL replay summaries."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = PROJECT_ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from agent.replay import format_replay_markdown, load_replay, load_replay_from_file  # noqa: E402


def agent_events_dir(project_root) -> Path:
    return Path(project_root) / "runtime" / "agent_events"


def find_latest_event_log(project_root) -> Optional[Path]:
    directory = agent_events_dir(project_root)
    if not directory.exists() or not directory.is_dir():
        return None
    files = [path for path in directory.glob("*.jsonl") if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def _mtime_text(timestamp: float) -> str:
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def list_event_logs(project_root) -> List[dict]:
    directory = agent_events_dir(project_root)
    if not directory.exists() or not directory.is_dir():
        return []

    items = []
    for path in directory.glob("*.jsonl"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except Exception:
            continue
        items.append(
            {
                "name": path.name,
                "path": str(path),
                "size": stat.st_size,
                "mtime": _mtime_text(stat.st_mtime),
                "_mtime_sort": stat.st_mtime,
            }
        )
    items.sort(key=lambda item: item.get("_mtime_sort", 0), reverse=True)
    for item in items:
        item.pop("_mtime_sort", None)
    return items


def format_event_log_list(items) -> str:
    if not items:
        return "No agent event logs found.\n"

    lines = [
        "| File | Size | Modified |",
        "|---|---:|---|",
    ]
    for item in items:
        lines.append(
            "| {name} | {size} | {mtime} |".format(
                name=str(item.get("name", "")).replace("|", "\\|"),
                size=item.get("size", 0),
                mtime=str(item.get("mtime", "")).replace("|", "\\|"),
            )
        )
    return "\n".join(lines) + "\n"


def summary_to_json(summary) -> str:
    return json.dumps(summary.to_dict(), ensure_ascii=False, indent=2)


def _resolve_path(project_root, value) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path(project_root) / path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect read-only Agent replay JSONL logs.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="Project root path.")
    parser.add_argument("--run-id", default="", help="Run id under runtime/agent_events.")
    parser.add_argument("--file", default="", help="Direct JSONL file path.")
    parser.add_argument("--latest", action="store_true", help="Read the newest JSONL event log.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Output format.")
    parser.add_argument("--list", action="store_true", help="List available JSONL event logs.")
    return parser


def _print_summary(summary, output_format: str):
    if output_format == "json":
        print(summary_to_json(summary))
    else:
        print(format_replay_markdown(summary), end="")


def run_cli(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve(strict=False)

    if args.list:
        print(format_event_log_list(list_event_logs(project_root)), end="")
        return 0

    if args.file:
        path = _resolve_path(project_root, args.file)
        if not path.exists() or not path.is_file():
            print(f"Agent event log file not found: {path}", file=sys.stderr)
            return 1
        _print_summary(load_replay_from_file(path), args.format)
        return 0

    if args.run_id:
        path = agent_events_dir(project_root) / f"{args.run_id}.jsonl"
        if not path.exists() or not path.is_file():
            print(f"Agent event log not found for run id '{args.run_id}': {path}", file=sys.stderr)
            return 1
        _print_summary(load_replay(project_root, args.run_id), args.format)
        return 0

    if args.latest:
        path = find_latest_event_log(project_root)
        if path is None:
            print(f"No agent event logs found under: {agent_events_dir(project_root)}", file=sys.stderr)
            return 1
        _print_summary(load_replay_from_file(path), args.format)
        return 0

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli())

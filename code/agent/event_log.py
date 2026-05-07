#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""JSONL event log helpers for the read-only Hybrid Agent layer.

This module only persists and reads AgentEvent records. It does not observe
browser state, execute actions, call LLM/VLM APIs, or import legacy players.
"""

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, List, Optional
import json
import uuid

from agent.schemas import AgentEvent


EVENT_LOG_DIR = Path("runtime") / "agent_events"


def ensure_event_log_dir(project_root) -> Path:
    """Create and return the runtime/agent_events directory."""
    path = Path(project_root) / EVENT_LOG_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_run_id(prefix="agent") -> str:
    """Return a readable run id with a short uuid suffix to avoid collisions."""
    safe_prefix = str(prefix or "agent").strip() or "agent"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return f"{safe_prefix}_{stamp}_{suffix}"


def event_log_path(project_root, run_id) -> Path:
    """Return the JSONL path for a run id and ensure the log directory exists."""
    return ensure_event_log_dir(project_root) / f"{run_id}.jsonl"


def safe_read_jsonl(path) -> List[AgentEvent]:
    """Read valid AgentEvent lines from a JSONL file, skipping damaged lines."""
    log_path = Path(path)
    if not log_path.exists() or not log_path.is_file():
        return []

    events = []
    try:
        with log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    data = json.loads(text)
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                events.append(AgentEvent.from_dict(data))
    except Exception:
        return events
    return events


def summarize_events(events: Iterable[AgentEvent]) -> dict:
    """Build a lightweight summary for a sequence of events."""
    event_list = list(events or [])
    event_types = Counter(event.event_type for event in event_list)
    timestamps = [event.timestamp for event in event_list if event.timestamp]
    first = timestamps[0] if timestamps else ""
    last = timestamps[-1] if timestamps else ""
    run_id = event_list[0].run_id if event_list else ""
    has_error = any(event.event_type == "error" or bool(event.error) for event in event_list)

    return {
        "run_id": run_id,
        "path": "",
        "event_count": len(event_list),
        "event_types": dict(event_types),
        "first_timestamp": first,
        "last_timestamp": last,
        "has_error": has_error,
    }


class AgentEventLog:
    """Append/read JSONL events for one run.

    append() normalizes every event's run_id to this log's run_id before writing.
    That keeps a single JSONL file replayable even when callers pass partially
    populated or reused AgentEvent instances.
    """

    def __init__(self, project_root, run_id=None, auto_create=True):
        self.project_root = Path(project_root)
        self.run_id = str(run_id or new_run_id()).strip() or new_run_id()
        if auto_create:
            self.path = event_log_path(self.project_root, self.run_id)
        else:
            self.path = self.project_root / EVENT_LOG_DIR / f"{self.run_id}.jsonl"
        self.closed = False

    def append(self, event: AgentEvent) -> Path:
        """Append one AgentEvent as one JSONL line and return the log path."""
        if not isinstance(event, AgentEvent):
            event = AgentEvent.from_dict(event)

        data = event.to_dict()
        data["run_id"] = self.run_id
        normalized = AgentEvent.from_dict(data)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(normalized.to_json_line())
        return self.path

    def append_event(self, event_type, **kwargs) -> AgentEvent:
        """Create, append, and return an AgentEvent for this log."""
        event = AgentEvent(
            event_type=event_type,
            run_id=self.run_id,
            step_index=kwargs.get("step_index", 0),
            mode=kwargs.get("mode", ""),
            account_file=kwargs.get("account_file", ""),
            url=kwargs.get("url", ""),
            state=kwargs.get("state"),
            observation=kwargs.get("observation"),
            proposal=kwargs.get("proposal"),
            last_action=kwargs.get("last_action", {}),
            error=kwargs.get("error", ""),
            notes=kwargs.get("notes", ""),
        )
        self.append(event)
        return event

    def read_all(self) -> List[AgentEvent]:
        """Read all valid events in the current JSONL file."""
        return safe_read_jsonl(self.path)

    def iter_events(self, event_type=None) -> Iterator[AgentEvent]:
        """Iterate events, optionally filtering by event_type."""
        for event in self.read_all():
            if event_type is None or event.event_type == event_type:
                yield event

    def summary(self) -> dict:
        """Return a lightweight summary for the current log file."""
        data = summarize_events(self.read_all())
        data["run_id"] = self.run_id
        data["path"] = str(self.path)
        return data

    def close(self):
        """Mark the log closed; append opens/closes files per write."""
        self.closed = True


def write_event(project_root, run_id, event: AgentEvent) -> Path:
    """Append a single event to a run's JSONL file."""
    return AgentEventLog(project_root, run_id=run_id).append(event)


def read_events(project_root, run_id) -> List[AgentEvent]:
    """Read all valid events for a run id."""
    return safe_read_jsonl(event_log_path(project_root, run_id))


__all__ = [
    "AgentEventLog",
    "ensure_event_log_dir",
    "event_log_path",
    "new_run_id",
    "read_events",
    "safe_read_jsonl",
    "summarize_events",
    "write_event",
]

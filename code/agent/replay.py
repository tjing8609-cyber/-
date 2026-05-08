#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Read-only replay summaries for Agent JSONL event logs."""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, List

from agent.event_log import EVENT_LOG_DIR, safe_read_jsonl
from agent.schemas import AgentEvent, ObservationFrame, StateSnapshot, safe_list


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        return str(value)
    except Exception:
        return default


def _clip(value: Any, limit: int = 300) -> str:
    text = _text(value).strip()
    try:
        max_len = int(limit)
    except (TypeError, ValueError):
        max_len = 300
    if max_len <= 0:
        return ""
    return text[:max_len]


def _event(value: Any) -> AgentEvent:
    return value if isinstance(value, AgentEvent) else AgentEvent.from_dict(value)


def _observation_state(observation: Any) -> StateSnapshot:
    if isinstance(observation, ObservationFrame):
        return observation.state
    frame = ObservationFrame.from_dict(observation)
    return frame.state


def _event_state(event: AgentEvent) -> StateSnapshot:
    if isinstance(event.state, StateSnapshot):
        return event.state
    if event.observation is not None:
        return _observation_state(event.observation)
    return StateSnapshot()


@dataclass
class ReplaySummary:
    run_id: str = ""
    event_count: int = 0
    event_types: dict = field(default_factory=dict)
    first_timestamp: str = ""
    last_timestamp: str = ""
    start_event: dict = field(default_factory=dict)
    complete_event: dict = field(default_factory=dict)
    error_events: list = field(default_factory=list)
    observe_events: list = field(default_factory=list)
    state_timeline: list = field(default_factory=list)
    url_timeline: list = field(default_factory=list)
    title_timeline: list = field(default_factory=list)
    notes_timeline: list = field(default_factory=list)
    has_error: bool = False
    completed: bool = False

    def to_dict(self):
        return {
            "run_id": self.run_id,
            "event_count": self.event_count,
            "event_types": dict(self.event_types),
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "start_event": dict(self.start_event),
            "complete_event": dict(self.complete_event),
            "error_events": [dict(item) for item in self.error_events],
            "observe_events": [dict(item) for item in self.observe_events],
            "state_timeline": [dict(item) for item in self.state_timeline],
            "url_timeline": [dict(item) for item in self.url_timeline],
            "title_timeline": [dict(item) for item in self.title_timeline],
            "notes_timeline": [dict(item) for item in self.notes_timeline],
            "has_error": bool(self.has_error),
            "completed": bool(self.completed),
        }


def event_to_digest(event: AgentEvent) -> dict:
    try:
        item = _event(event)
    except Exception:
        item = AgentEvent()

    observation = item.observation if isinstance(item.observation, ObservationFrame) else None
    state = _event_state(item)
    digest = {
        "timestamp": _clip(item.timestamp, 80),
        "event_type": _clip(item.event_type, 80),
        "step_index": item.step_index,
        "mode": _clip(item.mode, 100),
        "url": _clip(item.url or (observation.url if observation else ""), 500),
        "state": _clip(state.primary_state, 100),
        "title": _clip(observation.title if observation else "", 200),
        "notes": _clip(item.notes, 500),
        "error": _clip(item.error, 500),
    }

    if observation is not None:
        obs_state = observation.state if isinstance(observation.state, StateSnapshot) else StateSnapshot.from_dict(observation.state)
        digest.update(
            {
                "observation_url": _clip(observation.url, 500),
                "observation_title": _clip(observation.title, 200),
                "primary_state": _clip(obs_state.primary_state, 100),
                "overlays": [_clip(value, 80) for value in safe_list(obs_state.overlays)],
                "task_phase": _clip(obs_state.task_phase, 100),
                "page_text_digest": _clip(getattr(observation, "page_text_digest", ""), 300),
            }
        )

    return digest


def summarize_replay(events: List[AgentEvent]) -> ReplaySummary:
    event_list = [_event(event) for event in list(events or [])]
    if not event_list:
        return ReplaySummary()

    digests = [event_to_digest(event) for event in event_list]
    event_types = Counter(event.event_type for event in event_list)
    timestamps = [event.timestamp for event in event_list if event.timestamp]
    start_events = [digest for digest in digests if digest["event_type"] == "run_start"]
    complete_events = [digest for digest in digests if digest["event_type"] == "run_complete"]
    error_events = [digest for digest in digests if digest["event_type"] == "error" or digest["error"]]
    observe_events = [digest for digest in digests if digest["event_type"] == "observe"]

    state_timeline = []
    url_timeline = []
    title_timeline = []
    notes_timeline = []
    for digest in digests:
        url = digest.get("observation_url") or digest.get("url", "")
        title = digest.get("observation_title") or digest.get("title", "")
        primary_state = digest.get("primary_state") or digest.get("state", "")
        notes = digest.get("notes", "")

        if url:
            url_timeline.append(
                {
                    "step_index": digest["step_index"],
                    "event_type": digest["event_type"],
                    "url": url,
                    "title": title,
                }
            )
        if title:
            title_timeline.append(
                {
                    "step_index": digest["step_index"],
                    "event_type": digest["event_type"],
                    "title": title,
                }
            )
        if primary_state:
            state_timeline.append(
                {
                    "step_index": digest["step_index"],
                    "event_type": digest["event_type"],
                    "primary_state": primary_state,
                    "overlays": list(digest.get("overlays", [])),
                    "task_phase": digest.get("task_phase", ""),
                    "notes": notes,
                }
            )
        if notes:
            notes_timeline.append(
                {
                    "step_index": digest["step_index"],
                    "event_type": digest["event_type"],
                    "notes": notes,
                }
            )

    return ReplaySummary(
        run_id=event_list[0].run_id,
        event_count=len(event_list),
        event_types=dict(event_types),
        first_timestamp=timestamps[0] if timestamps else "",
        last_timestamp=timestamps[-1] if timestamps else "",
        start_event=start_events[0] if start_events else {},
        complete_event=complete_events[-1] if complete_events else {},
        error_events=error_events,
        observe_events=observe_events,
        state_timeline=state_timeline,
        url_timeline=url_timeline,
        title_timeline=title_timeline,
        notes_timeline=notes_timeline,
        has_error=bool(error_events),
        completed=bool(complete_events),
    )


def load_replay_from_file(path) -> ReplaySummary:
    return summarize_replay(safe_read_jsonl(path))


def load_replay(project_root, run_id) -> ReplaySummary:
    path = Path(project_root) / EVENT_LOG_DIR / f"{run_id}.jsonl"
    return load_replay_from_file(path)


def _md_cell(value: Any, limit: int = 160) -> str:
    text = _clip(value, limit).replace("|", "\\|")
    return text.replace("\n", " ")


def _md_list(values: Iterable[Any]) -> str:
    items = [_md_cell(value, 80) for value in values or [] if _md_cell(value, 80)]
    return ", ".join(items)


def format_replay_markdown(summary: ReplaySummary) -> str:
    data = summary if isinstance(summary, ReplaySummary) else ReplaySummary()
    if data.event_count <= 0:
        return "# Agent Replay Summary\n\nNo events recorded.\n"

    lines = [
        "# Agent Replay Summary",
        "",
        f"- Run ID: {_md_cell(data.run_id, 200)}",
        f"- Events: {data.event_count}",
        f"- Completed: {data.completed}",
        f"- Has Error: {data.has_error}",
        f"- First Timestamp: {_md_cell(data.first_timestamp, 100)}",
        f"- Last Timestamp: {_md_cell(data.last_timestamp, 100)}",
        "",
        "## Event Types",
        "",
        "| Event Type | Count |",
        "|---|---:|",
    ]
    for event_type, count in sorted(data.event_types.items()):
        lines.append(f"| {_md_cell(event_type)} | {count} |")

    lines.extend(
        [
            "",
            "## URL Timeline",
            "",
            "| Step | Event | URL | Title |",
            "|---:|---|---|---|",
        ]
    )
    if data.url_timeline:
        for item in data.url_timeline:
            lines.append(
                "| {step} | {event} | {url} | {title} |".format(
                    step=item.get("step_index", 0),
                    event=_md_cell(item.get("event_type", "")),
                    url=_md_cell(item.get("url", ""), 220),
                    title=_md_cell(item.get("title", ""), 160),
                )
            )
    else:
        lines.append("|  |  | no urls |  |")

    lines.extend(
        [
            "",
            "## State Timeline",
            "",
            "| Step | Primary State | Overlays | Notes |",
            "|---:|---|---|---|",
        ]
    )
    if data.state_timeline:
        for item in data.state_timeline:
            lines.append(
                "| {step} | {state} | {overlays} | {notes} |".format(
                    step=item.get("step_index", 0),
                    state=_md_cell(item.get("primary_state", "")),
                    overlays=_md_list(item.get("overlays", [])),
                    notes=_md_cell(item.get("notes", ""), 220),
                )
            )
    else:
        lines.append("|  | no states |  |  |")

    lines.extend(["", "## Errors", ""])
    if data.error_events:
        for item in data.error_events:
            lines.append(
                "- [{timestamp}] step={step} {error} {notes}".format(
                    timestamp=_md_cell(item.get("timestamp", ""), 100),
                    step=item.get("step_index", 0),
                    error=_md_cell(item.get("error", ""), 240),
                    notes=_md_cell(item.get("notes", ""), 160),
                ).rstrip()
            )
    else:
        lines.append("No errors recorded.")

    return "\n".join(lines) + "\n"


def replay_to_dict(project_root, run_id) -> dict:
    return load_replay(project_root, run_id).to_dict()


__all__ = [
    "ReplaySummary",
    "event_to_digest",
    "format_replay_markdown",
    "load_replay",
    "load_replay_from_file",
    "replay_to_dict",
    "summarize_replay",
]

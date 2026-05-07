#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pure data schemas for the first read-only Hybrid Agent layer.

This module intentionally has no Selenium, browser, LLM, VLM, or legacy player
imports. It only defines stable, JSON-friendly records for observation and
future replay.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from typing import Any, Dict, List, Optional


def utc_timestamp() -> str:
    """Return a compact UTC timestamp suitable for JSONL event logs."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def current_timestamp() -> str:
    """Alias kept for callers that prefer local wording over UTC wording."""
    return utc_timestamp()


def safe_dict(value: Any) -> Dict[str, Any]:
    """Best-effort conversion to a shallow dict without raising on bad input."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            data = to_dict()
            return dict(data) if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def safe_list(value: Any) -> List[Any]:
    """Best-effort conversion to a list without treating strings as iterables."""
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def clamp_confidence(value: Any) -> float:
    """Clamp confidence values into the inclusive 0.0 to 1.0 range."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    if number < 0.0:
        return 0.0
    if number > 1.0:
        return 1.0
    return number


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        text = str(value)
    except Exception:
        return default
    return text


def _int_or_default(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_safe(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        return f"<bytes {len(value)}>"
    return str(value)


def json_dumps_line(data: Any) -> str:
    """Serialize one stable UTF-8-friendly JSONL line."""
    return json.dumps(
        _json_safe(data),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


@dataclass
class StateSnapshot:
    primary_state: str = "unknown"
    overlays: List[str] = field(default_factory=list)
    flags: Dict[str, Any] = field(default_factory=dict)
    task_phase: str = "unknown"
    confidence: float = 0.0
    reason: str = ""

    def __post_init__(self):
        self.primary_state = _text(self.primary_state, "unknown") or "unknown"
        self.overlays = [_text(item) for item in safe_list(self.overlays) if _text(item)]
        self.flags = safe_dict(self.flags)
        self.task_phase = _text(self.task_phase, "unknown") or "unknown"
        self.confidence = clamp_confidence(self.confidence)
        self.reason = _text(self.reason)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary_state": self.primary_state,
            "overlays": list(self.overlays),
            "flags": dict(self.flags),
            "task_phase": self.task_phase,
            "confidence": self.confidence,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "StateSnapshot":
        value = safe_dict(data)
        return cls(
            primary_state=value.get("primary_state", "unknown"),
            overlays=safe_list(value.get("overlays")),
            flags=safe_dict(value.get("flags")),
            task_phase=value.get("task_phase", "unknown"),
            confidence=value.get("confidence", 0.0),
            reason=value.get("reason", ""),
        )


@dataclass
class ObservationFrame:
    url: str = ""
    title: str = ""
    mode: str = ""
    course_name: str = ""
    timestamp: str = field(default_factory=current_timestamp)
    state: StateSnapshot = field(default_factory=StateSnapshot)
    video_state: Dict[str, Any] = field(default_factory=dict)
    dialogs: List[Dict[str, Any]] = field(default_factory=list)
    elements_digest: List[Dict[str, Any]] = field(default_factory=list)
    screenshot_path: str = ""
    html_snapshot_path: str = ""
    som_image_path: str = ""
    notes: str = ""

    def __post_init__(self):
        self.url = _text(self.url)
        self.title = _text(self.title)
        self.mode = _text(self.mode)
        self.course_name = _text(self.course_name)
        self.timestamp = _text(self.timestamp) or current_timestamp()
        self.state = self.state if isinstance(self.state, StateSnapshot) else StateSnapshot.from_dict(self.state)
        self.video_state = safe_dict(self.video_state)
        self.dialogs = [safe_dict(item) for item in safe_list(self.dialogs)]
        self.elements_digest = [safe_dict(item) for item in safe_list(self.elements_digest)]
        self.screenshot_path = _text(self.screenshot_path)
        self.html_snapshot_path = _text(self.html_snapshot_path)
        self.som_image_path = _text(self.som_image_path)
        self.notes = _text(self.notes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "mode": self.mode,
            "course_name": self.course_name,
            "timestamp": self.timestamp,
            "state": self.state.to_dict(),
            "video_state": dict(self.video_state),
            "dialogs": [dict(item) for item in self.dialogs],
            "elements_digest": [dict(item) for item in self.elements_digest],
            "screenshot_path": self.screenshot_path,
            "html_snapshot_path": self.html_snapshot_path,
            "som_image_path": self.som_image_path,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "ObservationFrame":
        value = safe_dict(data)
        return cls(
            url=value.get("url", ""),
            title=value.get("title", ""),
            mode=value.get("mode", ""),
            course_name=value.get("course_name", ""),
            timestamp=value.get("timestamp") or current_timestamp(),
            state=StateSnapshot.from_dict(value.get("state")),
            video_state=safe_dict(value.get("video_state")),
            dialogs=[safe_dict(item) for item in safe_list(value.get("dialogs"))],
            elements_digest=[safe_dict(item) for item in safe_list(value.get("elements_digest"))],
            screenshot_path=value.get("screenshot_path", ""),
            html_snapshot_path=value.get("html_snapshot_path", ""),
            som_image_path=value.get("som_image_path", ""),
            notes=value.get("notes", ""),
        )

    @classmethod
    def minimal(
        cls,
        url: str = "",
        title: str = "",
        mode: str = "",
        course_name: str = "",
        state: Optional[StateSnapshot] = None,
        notes: str = "",
    ) -> "ObservationFrame":
        return cls(
            url=url,
            title=title,
            mode=mode,
            course_name=course_name,
            state=state or StateSnapshot(),
            notes=notes,
        )


@dataclass
class ActionProposal:
    source: str = ""
    action_type: str = "noop"
    target_id: Optional[int] = None
    target_hint: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""
    approved: bool = False
    rejected_reason: str = ""

    def __post_init__(self):
        self.source = _text(self.source)
        self.action_type = _text(self.action_type, "noop") or "noop"
        self.target_id = _optional_int(self.target_id)
        self.target_hint = _text(self.target_hint)
        self.payload = safe_dict(self.payload)
        self.confidence = clamp_confidence(self.confidence)
        self.reason = _text(self.reason)
        self.approved = bool(self.approved)
        self.rejected_reason = _text(self.rejected_reason)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "action_type": self.action_type,
            "target_id": self.target_id,
            "target_hint": self.target_hint,
            "payload": dict(self.payload),
            "confidence": self.confidence,
            "reason": self.reason,
            "approved": self.approved,
            "rejected_reason": self.rejected_reason,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "ActionProposal":
        value = safe_dict(data)
        return cls(
            source=value.get("source", ""),
            action_type=value.get("action_type", "noop"),
            target_id=value.get("target_id"),
            target_hint=value.get("target_hint", ""),
            payload=safe_dict(value.get("payload")),
            confidence=value.get("confidence", 0.0),
            reason=value.get("reason", ""),
            approved=value.get("approved", False),
            rejected_reason=value.get("rejected_reason", ""),
        )

    @classmethod
    def noop(cls, reason: str = "") -> "ActionProposal":
        return cls(source="rule_engine", action_type="noop", reason=reason, confidence=1.0)


@dataclass
class AgentEvent:
    timestamp: str = field(default_factory=current_timestamp)
    event_type: str = "observe"
    run_id: str = ""
    step_index: int = 0
    mode: str = ""
    account_file: str = ""
    url: str = ""
    state: Optional[StateSnapshot] = None
    observation: Optional[ObservationFrame] = None
    proposal: Optional[ActionProposal] = None
    last_action: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    notes: str = ""

    def __post_init__(self):
        self.timestamp = _text(self.timestamp) or current_timestamp()
        self.event_type = _text(self.event_type, "observe") or "observe"
        self.run_id = _text(self.run_id)
        self.step_index = _int_or_default(self.step_index)
        self.mode = _text(self.mode)
        self.account_file = _text(self.account_file)
        self.url = _text(self.url)
        self.state = self._coerce_state(self.state)
        self.observation = self._coerce_observation(self.observation)
        self.proposal = self._coerce_proposal(self.proposal)
        self.last_action = safe_dict(self.last_action)
        self.error = _text(self.error)
        self.notes = _text(self.notes)

    @staticmethod
    def _coerce_state(value: Any) -> Optional[StateSnapshot]:
        if value is None:
            return None
        return value if isinstance(value, StateSnapshot) else StateSnapshot.from_dict(value)

    @staticmethod
    def _coerce_observation(value: Any) -> Optional[ObservationFrame]:
        if value is None:
            return None
        return value if isinstance(value, ObservationFrame) else ObservationFrame.from_dict(value)

    @staticmethod
    def _coerce_proposal(value: Any) -> Optional[ActionProposal]:
        if value is None:
            return None
        return value if isinstance(value, ActionProposal) else ActionProposal.from_dict(value)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "run_id": self.run_id,
            "step_index": self.step_index,
            "mode": self.mode,
            "account_file": self.account_file,
            "url": self.url,
            "state": self.state.to_dict() if self.state else None,
            "observation": self.observation.to_dict() if self.observation else None,
            "proposal": self.proposal.to_dict() if self.proposal else None,
            "last_action": dict(self.last_action),
            "error": self.error,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "AgentEvent":
        value = safe_dict(data)
        return cls(
            timestamp=value.get("timestamp") or current_timestamp(),
            event_type=value.get("event_type", "observe"),
            run_id=value.get("run_id", ""),
            step_index=value.get("step_index", 0),
            mode=value.get("mode", ""),
            account_file=value.get("account_file", ""),
            url=value.get("url", ""),
            state=value.get("state"),
            observation=value.get("observation"),
            proposal=value.get("proposal"),
            last_action=safe_dict(value.get("last_action")),
            error=value.get("error", ""),
            notes=value.get("notes", ""),
        )

    def to_json_line(self) -> str:
        return json_dumps_line(self.to_dict())

    @classmethod
    def from_json_line(cls, line: Any) -> "AgentEvent":
        try:
            data = json.loads(_text(line).strip() or "{}")
        except Exception:
            data = {}
        return cls.from_dict(data)


__all__ = [
    "ActionProposal",
    "AgentEvent",
    "ObservationFrame",
    "StateSnapshot",
    "clamp_confidence",
    "current_timestamp",
    "json_dumps_line",
    "safe_dict",
    "safe_list",
    "utc_timestamp",
]

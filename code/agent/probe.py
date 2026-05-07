#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Read-only Agent probe that combines Observer and EventLog."""

from dataclasses import dataclass
from typing import Any, Optional

from agent.event_log import AgentEventLog
from agent.observer import AgentObserver, observe_to_event
from agent.schemas import AgentEvent, ObservationFrame


@dataclass
class ProbeOptions:
    enabled: bool = True
    swallow_errors: bool = True
    default_event_type: str = "observe"
    auto_increment_step: bool = True


@dataclass
class ProbeRecordResult:
    ok: bool
    event: Optional[AgentEvent] = None
    observation: Optional[ObservationFrame] = None
    path: str = ""
    error: str = ""
    skipped: bool = False
    reason: str = ""

    def to_dict(self):
        return {
            "ok": bool(self.ok),
            "event": self.event.to_dict() if self.event else None,
            "observation": self.observation.to_dict() if self.observation else None,
            "path": self.path,
            "error": self.error,
            "skipped": bool(self.skipped),
            "reason": self.reason,
        }


class AgentProbe:
    """Read-only sidecar probe for recording observations and events.

    The probe is a coordinator only. It does not inspect browser-specific
    objects directly, execute browser actions, call APIs, or create screenshots.
    """

    def __init__(
        self,
        project_root,
        run_id=None,
        *,
        observer=None,
        event_log=None,
        options=None,
    ):
        self.project_root = project_root
        self.options = options if isinstance(options, ProbeOptions) else ProbeOptions()
        self.observer = observer if observer is not None else AgentObserver()
        self.event_log = event_log if event_log is not None else AgentEventLog(
            project_root,
            run_id=run_id,
            auto_create=self.options.enabled,
        )
        self.run_id = str(run_id or getattr(self.event_log, "run_id", "") or "")
        self._step_index = 0

    def next_step_index(self) -> int:
        value = self._step_index
        self._step_index += 1
        return value

    def _resolve_step_index(self, step_index):
        if step_index is not None:
            try:
                return int(step_index)
            except (TypeError, ValueError):
                return 0
        if self.options.auto_increment_step:
            return self.next_step_index()
        return 0

    def _disabled_result(self):
        return ProbeRecordResult(ok=True, skipped=True, reason="probe disabled")

    def _handle_error(self, error):
        if not self.options.swallow_errors:
            raise error
        return ProbeRecordResult(ok=False, error=str(error))

    def record_observation(
        self,
        driver=None,
        *,
        mode="",
        course_name="",
        video_state=None,
        dialogs=None,
        state=None,
        screenshot_path="",
        html_snapshot_path="",
        som_image_path="",
        account_file="",
        step_index=None,
        event_type=None,
        last_action=None,
        error="",
        notes="",
    ) -> ProbeRecordResult:
        if not self.options.enabled:
            return self._disabled_result()

        try:
            resolved_step = self._resolve_step_index(step_index)
            resolved_event_type = event_type or self.options.default_event_type
            observation = self.observer.observe(
                driver,
                mode=mode,
                course_name=course_name,
                video_state=video_state,
                dialogs=dialogs,
                state=state,
                screenshot_path=screenshot_path,
                html_snapshot_path=html_snapshot_path,
                som_image_path=som_image_path,
                notes=notes,
            )
            event = observe_to_event(
                observation,
                run_id=self.run_id,
                step_index=resolved_step,
                event_type=resolved_event_type,
                account_file=account_file,
                last_action=last_action,
                error=error,
                notes=notes,
            )
            path = self.event_log.append(event)
            return ProbeRecordResult(
                ok=True,
                event=event,
                observation=observation,
                path=str(path),
            )
        except Exception as exc:
            return self._handle_error(exc)

    def record_event(self, event_type, **kwargs) -> ProbeRecordResult:
        if not self.options.enabled:
            return self._disabled_result()

        try:
            if "step_index" not in kwargs or kwargs.get("step_index") is None:
                kwargs["step_index"] = self._resolve_step_index(None)
            event = self.event_log.append_event(event_type, **kwargs)
            return ProbeRecordResult(
                ok=True,
                event=event,
                path=str(getattr(self.event_log, "path", "")),
            )
        except Exception as exc:
            return self._handle_error(exc)

    def record_error(self, error, **kwargs) -> ProbeRecordResult:
        kwargs["error"] = str(error)
        return self.record_event("error", **kwargs)

    def summary(self) -> dict:
        if not self.options.enabled:
            return {"enabled": False, "event_count": 0}
        try:
            data = self.event_log.summary()
            data["enabled"] = True
            return data
        except Exception as exc:
            if not self.options.swallow_errors:
                raise
            return {"enabled": True, "event_count": 0, "error": str(exc)}

    def close(self):
        try:
            close = getattr(self.event_log, "close", None)
            if callable(close):
                close()
        except Exception as exc:
            if not self.options.swallow_errors:
                raise exc


def create_probe(project_root, run_id=None, enabled=True) -> AgentProbe:
    return AgentProbe(project_root, run_id=run_id, options=ProbeOptions(enabled=enabled))


def record_observation_once(project_root, driver=None, **kwargs) -> ProbeRecordResult:
    probe = create_probe(project_root, run_id=kwargs.pop("run_id", None), enabled=kwargs.pop("enabled", True))
    try:
        return probe.record_observation(driver, **kwargs)
    finally:
        probe.close()


__all__ = [
    "AgentProbe",
    "ProbeOptions",
    "ProbeRecordResult",
    "create_probe",
    "record_observation_once",
]

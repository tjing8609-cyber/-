#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Thin read-only adapter for future Agent probe instrumentation."""

from dataclasses import dataclass
from typing import Optional

from agent.probe import AgentProbe
from agent.probe_config import AgentProbeConfig, load_probe_config, to_probe_options


@dataclass
class ProbeHandle:
    config: AgentProbeConfig
    probe: Optional[AgentProbe] = None
    project_root: str = ""
    run_id: str = ""
    enabled: bool = False
    reason: str = ""

    def __post_init__(self):
        if not isinstance(self.config, AgentProbeConfig):
            self.config = AgentProbeConfig.from_dict({})
        self.enabled = bool(self.config.enabled and self.enabled and self.probe is not None)
        self.project_root = str(self.project_root or "")
        self.run_id = str(self.run_id or getattr(self.probe, "run_id", "") or self.config.run_id or "")
        self.reason = str(self.reason or "")

    def to_dict(self):
        return {
            "config": self.config.to_dict(),
            "has_probe": self.probe is not None,
            "project_root": self.project_root,
            "run_id": self.run_id,
            "enabled": self.enabled,
            "reason": self.reason,
        }


@dataclass
class AdapterRecordResult:
    ok: bool
    skipped: bool = False
    event_type: str = ""
    path: str = ""
    error: str = ""
    reason: str = ""

    def to_dict(self):
        return {
            "ok": bool(self.ok),
            "skipped": bool(self.skipped),
            "event_type": self.event_type,
            "path": self.path,
            "error": self.error,
            "reason": self.reason,
        }


def _swallow_errors(handle) -> bool:
    config = getattr(handle, "config", None)
    if isinstance(config, AgentProbeConfig):
        return bool(config.swallow_errors)
    return True


def _handle_exception(handle, event_type: str, error: Exception) -> AdapterRecordResult:
    if not _swallow_errors(handle):
        raise error
    return AdapterRecordResult(ok=False, event_type=event_type, error=str(error))


def _result_from_probe_result(event_type: str, probe_result) -> AdapterRecordResult:
    if probe_result is None:
        return AdapterRecordResult(
            ok=False,
            event_type=event_type,
            error="probe returned no result",
        )

    event = getattr(probe_result, "event", None)
    resolved_event_type = event_type or str(getattr(event, "event_type", "") or "")
    return AdapterRecordResult(
        ok=bool(getattr(probe_result, "ok", False)),
        skipped=bool(getattr(probe_result, "skipped", False)),
        event_type=resolved_event_type,
        path=str(getattr(probe_result, "path", "") or ""),
        error=str(getattr(probe_result, "error", "") or ""),
        reason=str(getattr(probe_result, "reason", "") or ""),
    )


def create_probe_handle(project_root, account_config=None, env=None) -> ProbeHandle:
    config = load_probe_config(account_config, env)
    root = str(project_root or "")

    if not config.enabled:
        return ProbeHandle(
            config=config,
            probe=None,
            project_root=root,
            run_id=config.run_id,
            enabled=False,
            reason="probe disabled",
        )

    try:
        options = to_probe_options(config)
        probe = AgentProbe(root, run_id=config.run_id or None, options=options)
        return ProbeHandle(
            config=config,
            probe=probe,
            project_root=root,
            run_id=getattr(probe, "run_id", config.run_id),
            enabled=True,
        )
    except Exception as exc:
        if not config.swallow_errors:
            raise
        return ProbeHandle(
            config=config,
            probe=None,
            project_root=root,
            run_id=config.run_id,
            enabled=False,
            reason=str(exc),
        )


def is_probe_enabled(handle) -> bool:
    if handle is None:
        return False
    if not getattr(handle, "enabled", False):
        return False
    if getattr(handle, "probe", None) is None:
        return False
    return True


def skipped_result(event_type: str = "", reason: str = "probe disabled") -> AdapterRecordResult:
    return AdapterRecordResult(ok=True, skipped=True, event_type=event_type, reason=reason)


def record_probe_start(handle, **kwargs) -> AdapterRecordResult:
    event_type = "run_start"
    if not is_probe_enabled(handle):
        return skipped_result(event_type)
    if not getattr(handle.config, "record_start", True):
        return skipped_result(event_type, "record_start disabled")

    try:
        result = handle.probe.record_event(event_type, **kwargs)
        return _result_from_probe_result(event_type, result)
    except Exception as exc:
        return _handle_exception(handle, event_type, exc)


def record_probe_observation(handle, driver=None, **kwargs) -> AdapterRecordResult:
    event_type = kwargs.get("event_type") or getattr(getattr(handle, "config", None), "default_event_type", "observe")
    if not is_probe_enabled(handle):
        return skipped_result(event_type)

    try:
        result = handle.probe.record_observation(driver=driver, **kwargs)
        return _result_from_probe_result(event_type, result)
    except Exception as exc:
        return _handle_exception(handle, event_type, exc)


def record_probe_legacy_action(
    handle,
    action_name: str = "",
    details: Optional[dict] = None,
    **kwargs,
) -> AdapterRecordResult:
    event_type = "legacy_action"
    if not is_probe_enabled(handle):
        return skipped_result(event_type)

    try:
        data = dict(kwargs)
        data["last_action"] = {
            "name": str(action_name or ""),
            "details": details or {},
        }
        result = handle.probe.record_event(event_type, **data)
        return _result_from_probe_result(event_type, result)
    except Exception as exc:
        return _handle_exception(handle, event_type, exc)


def record_probe_error(handle, error, **kwargs) -> AdapterRecordResult:
    event_type = "error"
    if not is_probe_enabled(handle):
        return skipped_result(event_type)
    if not getattr(handle.config, "record_error", True):
        return skipped_result(event_type, "record_error disabled")

    try:
        result = handle.probe.record_error(error, **kwargs)
        return _result_from_probe_result(event_type, result)
    except Exception as exc:
        return _handle_exception(handle, event_type, exc)


def record_probe_complete(handle, **kwargs) -> AdapterRecordResult:
    event_type = "run_complete"
    if not is_probe_enabled(handle):
        return skipped_result(event_type)
    if not getattr(handle.config, "record_complete", True):
        return skipped_result(event_type, "record_complete disabled")

    try:
        result = handle.probe.record_event(event_type, **kwargs)
        return _result_from_probe_result(event_type, result)
    except Exception as exc:
        return _handle_exception(handle, event_type, exc)


def close_probe_handle(handle) -> AdapterRecordResult:
    event_type = "close"
    if not is_probe_enabled(handle):
        return skipped_result(event_type)

    try:
        handle.probe.close()
        path = str(getattr(getattr(handle.probe, "event_log", None), "path", "") or "")
        return AdapterRecordResult(ok=True, event_type=event_type, path=path)
    except Exception as exc:
        return _handle_exception(handle, event_type, exc)


__all__ = [
    "AdapterRecordResult",
    "ProbeHandle",
    "close_probe_handle",
    "create_probe_handle",
    "is_probe_enabled",
    "record_probe_complete",
    "record_probe_error",
    "record_probe_legacy_action",
    "record_probe_observation",
    "record_probe_start",
    "skipped_result",
]

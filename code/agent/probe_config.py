#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Configuration parsing for the read-only Agent probe."""

from collections.abc import Mapping
from dataclasses import dataclass
import os
from typing import Any, Optional

from agent.probe import ProbeOptions


TRUE_VALUES = {"true", "1", "yes", "y", "on", "enabled", "开启", "启用"}
FALSE_VALUES = {"false", "0", "no", "n", "off", "disabled", "关闭", "禁用"}

CONFIG_ENV_KEYS = {
    "agent_probe_enabled": "ZHIDAO_AGENT_PROBE_ENABLED",
    "agent_probe_run_id": "ZHIDAO_AGENT_PROBE_RUN_ID",
    "agent_probe_event_type": "ZHIDAO_AGENT_PROBE_EVENT_TYPE",
    "agent_probe_swallow_errors": "ZHIDAO_AGENT_PROBE_SWALLOW_ERRORS",
    "agent_probe_auto_increment_step": "ZHIDAO_AGENT_PROBE_AUTO_INCREMENT_STEP",
    "agent_probe_notes": "ZHIDAO_AGENT_PROBE_NOTES",
    "agent_probe_record_start": "ZHIDAO_AGENT_PROBE_RECORD_START",
    "agent_probe_record_complete": "ZHIDAO_AGENT_PROBE_RECORD_COMPLETE",
    "agent_probe_record_error": "ZHIDAO_AGENT_PROBE_RECORD_ERROR",
}


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return bool(default)

    try:
        text = str(value).strip().lower()
    except Exception:
        return bool(default)

    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return bool(default)


def parse_string(value: Any, default: str = "", limit: int = 500) -> str:
    if value is None:
        return default

    try:
        max_length = int(limit)
    except (TypeError, ValueError):
        max_length = 500
    if max_length < 0:
        max_length = 0

    try:
        text = str(value).strip()
    except Exception:
        text = default

    if len(text) > max_length:
        return text[:max_length]
    return text


@dataclass
class AgentProbeConfig:
    enabled: bool = False
    run_id: str = ""
    default_event_type: str = "observe"
    swallow_errors: bool = True
    auto_increment_step: bool = True
    notes: str = ""
    record_start: bool = True
    record_complete: bool = True
    record_error: bool = True

    def __post_init__(self):
        self.enabled = parse_bool(self.enabled, False)
        self.run_id = parse_string(self.run_id, "")
        self.default_event_type = parse_string(self.default_event_type, "observe") or "observe"
        self.swallow_errors = parse_bool(self.swallow_errors, True)
        self.auto_increment_step = parse_bool(self.auto_increment_step, True)
        self.notes = parse_string(self.notes, "")
        self.record_start = parse_bool(self.record_start, True)
        self.record_complete = parse_bool(self.record_complete, True)
        self.record_error = parse_bool(self.record_error, True)

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "run_id": self.run_id,
            "default_event_type": self.default_event_type,
            "swallow_errors": self.swallow_errors,
            "auto_increment_step": self.auto_increment_step,
            "notes": self.notes,
            "record_start": self.record_start,
            "record_complete": self.record_complete,
            "record_error": self.record_error,
        }

    @classmethod
    def from_dict(cls, data):
        values = data if isinstance(data, dict) else {}
        defaults = cls()
        return cls(
            enabled=parse_bool(values.get("enabled", defaults.enabled), defaults.enabled),
            run_id=parse_string(values.get("run_id", defaults.run_id), defaults.run_id),
            default_event_type=parse_string(
                values.get("default_event_type", defaults.default_event_type),
                defaults.default_event_type,
            ) or defaults.default_event_type,
            swallow_errors=parse_bool(
                values.get("swallow_errors", defaults.swallow_errors),
                defaults.swallow_errors,
            ),
            auto_increment_step=parse_bool(
                values.get("auto_increment_step", defaults.auto_increment_step),
                defaults.auto_increment_step,
            ),
            notes=parse_string(values.get("notes", defaults.notes), defaults.notes),
            record_start=parse_bool(
                values.get("record_start", defaults.record_start),
                defaults.record_start,
            ),
            record_complete=parse_bool(
                values.get("record_complete", defaults.record_complete),
                defaults.record_complete,
            ),
            record_error=parse_bool(
                values.get("record_error", defaults.record_error),
                defaults.record_error,
            ),
        )


def default_probe_config() -> AgentProbeConfig:
    return AgentProbeConfig()


def _read_config_value(
    config: Optional[Mapping[str, Any]],
    env: Optional[Mapping[str, Any]],
    config_key: str,
    default: Any,
) -> Any:
    if isinstance(config, Mapping) and config_key in config:
        return config.get(config_key)

    env_key = CONFIG_ENV_KEYS.get(config_key, "")
    if isinstance(env, Mapping) and env_key in env:
        return env.get(env_key)

    return default


def load_probe_config(
    config: Optional[dict] = None,
    env: Optional[dict] = None,
) -> AgentProbeConfig:
    source_env = os.environ if env is None else env
    defaults = default_probe_config()

    return AgentProbeConfig(
        enabled=parse_bool(
            _read_config_value(config, source_env, "agent_probe_enabled", defaults.enabled),
            defaults.enabled,
        ),
        run_id=parse_string(
            _read_config_value(config, source_env, "agent_probe_run_id", defaults.run_id),
            defaults.run_id,
        ),
        default_event_type=parse_string(
            _read_config_value(
                config,
                source_env,
                "agent_probe_event_type",
                defaults.default_event_type,
            ),
            defaults.default_event_type,
        ) or defaults.default_event_type,
        swallow_errors=parse_bool(
            _read_config_value(
                config,
                source_env,
                "agent_probe_swallow_errors",
                defaults.swallow_errors,
            ),
            defaults.swallow_errors,
        ),
        auto_increment_step=parse_bool(
            _read_config_value(
                config,
                source_env,
                "agent_probe_auto_increment_step",
                defaults.auto_increment_step,
            ),
            defaults.auto_increment_step,
        ),
        notes=parse_string(
            _read_config_value(config, source_env, "agent_probe_notes", defaults.notes),
            defaults.notes,
        ),
        record_start=parse_bool(
            _read_config_value(
                config,
                source_env,
                "agent_probe_record_start",
                defaults.record_start,
            ),
            defaults.record_start,
        ),
        record_complete=parse_bool(
            _read_config_value(
                config,
                source_env,
                "agent_probe_record_complete",
                defaults.record_complete,
            ),
            defaults.record_complete,
        ),
        record_error=parse_bool(
            _read_config_value(
                config,
                source_env,
                "agent_probe_record_error",
                defaults.record_error,
            ),
            defaults.record_error,
        ),
    )


def to_probe_options(config: AgentProbeConfig) -> ProbeOptions:
    resolved = config if isinstance(config, AgentProbeConfig) else AgentProbeConfig.from_dict({})
    return ProbeOptions(
        enabled=resolved.enabled,
        swallow_errors=resolved.swallow_errors,
        default_event_type=resolved.default_event_type,
        auto_increment_step=resolved.auto_increment_step,
    )

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from agent.probe import ProbeOptions  # noqa: E402
from agent.probe_config import (  # noqa: E402
    AgentProbeConfig,
    default_probe_config,
    load_probe_config,
    parse_bool,
    parse_string,
    to_probe_options,
)


class AgentProbeConfigTests(unittest.TestCase):
    def test_default_probe_config_is_disabled(self):
        config = default_probe_config()

        self.assertFalse(config.enabled)
        self.assertTrue(config.swallow_errors)
        self.assertTrue(config.record_start)
        self.assertTrue(config.record_complete)
        self.assertTrue(config.record_error)

    def test_parse_bool_recognizes_true_strings(self):
        for value in ("true", "1", "yes", "y", "on", "enabled", "TRUE", " Yes "):
            with self.subTest(value=value):
                self.assertTrue(parse_bool(value))

    def test_parse_bool_recognizes_false_strings(self):
        for value in ("false", "0", "no", "n", "off", "disabled", "FALSE", " Off "):
            with self.subTest(value=value):
                self.assertFalse(parse_bool(value, default=True))

    def test_parse_bool_none_uses_default(self):
        self.assertTrue(parse_bool(None, default=True))

    def test_parse_bool_unknown_uses_default(self):
        self.assertFalse(parse_bool("unknown", default=False))

    def test_parse_bool_supports_chinese_values(self):
        self.assertTrue(parse_bool("开启"))
        self.assertTrue(parse_bool("启用"))
        self.assertFalse(parse_bool("关闭", default=True))
        self.assertFalse(parse_bool("禁用", default=True))

    def test_parse_string_handles_none(self):
        self.assertEqual(parse_string(None, default="fallback"), "fallback")

    def test_parse_string_truncates_long_text(self):
        self.assertEqual(parse_string("abcdef", limit=3), "abc")

    def test_config_to_dict_from_dict_round_trip(self):
        config = AgentProbeConfig(
            enabled=True,
            run_id="run-1",
            default_event_type="observe_once",
            swallow_errors=False,
            auto_increment_step=False,
            notes="旁路观察",
            record_start=False,
            record_complete=True,
            record_error=False,
        )

        restored = AgentProbeConfig.from_dict(config.to_dict())

        self.assertEqual(restored.to_dict(), config.to_dict())

    def test_from_dict_missing_fields_does_not_crash(self):
        config = AgentProbeConfig.from_dict({"enabled": "true"})

        self.assertTrue(config.enabled)
        self.assertEqual(config.run_id, "")
        self.assertEqual(config.default_event_type, "observe")
        self.assertTrue(config.swallow_errors)

    def test_load_probe_config_empty_defaults_disabled(self):
        config = load_probe_config({}, env={})

        self.assertFalse(config.enabled)

    def test_config_dict_has_priority_over_env(self):
        config = load_probe_config(
            {"agent_probe_enabled": "false", "agent_probe_run_id": "from-config"},
            env={
                "ZHIDAO_AGENT_PROBE_ENABLED": "true",
                "ZHIDAO_AGENT_PROBE_RUN_ID": "from-env",
            },
        )

        self.assertFalse(config.enabled)
        self.assertEqual(config.run_id, "from-config")

    def test_env_can_enable_probe(self):
        config = load_probe_config({}, env={"ZHIDAO_AGENT_PROBE_ENABLED": "on"})

        self.assertTrue(config.enabled)

    def test_env_can_set_run_id(self):
        config = load_probe_config({}, env={"ZHIDAO_AGENT_PROBE_RUN_ID": "agent-test"})

        self.assertEqual(config.run_id, "agent-test")

    def test_swallow_errors_parses_correctly(self):
        config = load_probe_config({"agent_probe_swallow_errors": "off"}, env={})

        self.assertFalse(config.swallow_errors)

    def test_auto_increment_step_parses_correctly(self):
        config = load_probe_config({"agent_probe_auto_increment_step": "0"}, env={})

        self.assertFalse(config.auto_increment_step)

    def test_record_flags_parse_correctly(self):
        config = load_probe_config(
            {
                "agent_probe_record_start": "false",
                "agent_probe_record_complete": "0",
                "agent_probe_record_error": "禁用",
            },
            env={},
        )

        self.assertFalse(config.record_start)
        self.assertFalse(config.record_complete)
        self.assertFalse(config.record_error)

    def test_to_probe_options_maps_fields(self):
        config = AgentProbeConfig(
            enabled=True,
            default_event_type="state_snapshot",
            swallow_errors=False,
            auto_increment_step=False,
        )

        options = to_probe_options(config)

        self.assertIsInstance(options, ProbeOptions)
        self.assertTrue(options.enabled)
        self.assertEqual(options.default_event_type, "state_snapshot")
        self.assertFalse(options.swallow_errors)
        self.assertFalse(options.auto_increment_step)

    def test_extra_fields_are_ignored(self):
        config = AgentProbeConfig.from_dict(
            {
                "enabled": "yes",
                "run_id": "run-extra",
                "unexpected": "ignored",
            }
        )

        self.assertTrue(config.enabled)
        self.assertEqual(config.run_id, "run-extra")
        self.assertNotIn("unexpected", config.to_dict())

    def test_chinese_notes_are_preserved(self):
        config = load_probe_config({"agent_probe_notes": "中文备注"}, env={})

        self.assertEqual(config.notes, "中文备注")


if __name__ == "__main__":
    unittest.main()

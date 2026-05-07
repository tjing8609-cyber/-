import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from agent.probe_adapter import (  # noqa: E402
    AdapterRecordResult,
    ProbeHandle,
    close_probe_handle,
    create_probe_handle,
    is_probe_enabled,
    record_probe_complete,
    record_probe_error,
    record_probe_legacy_action,
    record_probe_observation,
    record_probe_start,
)
from agent.probe_config import AgentProbeConfig  # noqa: E402


class FakeDriver:
    current_url = "https://example.com/course"
    title = "\u8bfe\u7a0b\u9875\u9762"
    page_source = "<html><body>\u8bfe\u7a0b\u76ee\u5f55 \u7ae0\u8282 \u7ee7\u7eed\u5b66\u4e60</body></html>"


class FailingProbe:
    run_id = "failing-run"

    def record_event(self, *args, **kwargs):
        raise RuntimeError("record failed")

    def record_observation(self, *args, **kwargs):
        raise RuntimeError("observe failed")

    def record_error(self, *args, **kwargs):
        raise RuntimeError("error failed")

    def close(self):
        raise RuntimeError("close failed")


class AgentProbeAdapterTests(unittest.TestCase):
    def test_create_probe_handle_defaults_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(tmp, env={})

            self.assertFalse(handle.enabled)
            self.assertFalse(is_probe_enabled(handle))
            self.assertEqual(handle.reason, "probe disabled")

    def test_default_disabled_does_not_create_agent_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(tmp, env={})

            self.assertIsNone(handle.probe)

    def test_default_disabled_does_not_create_runtime_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_probe_handle(tmp, env={})

            self.assertFalse((Path(tmp) / "runtime" / "agent_events").exists())

    def test_env_enabled_creates_enabled_handle(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(tmp, env={"ZHIDAO_AGENT_PROBE_ENABLED": "true"})

            self.assertTrue(handle.enabled)
            self.assertTrue(is_probe_enabled(handle))
            self.assertIsNotNone(handle.probe)

    def test_config_dict_has_priority_over_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(
                tmp,
                {"agent_probe_enabled": "false"},
                env={"ZHIDAO_AGENT_PROBE_ENABLED": "true"},
            )

            self.assertFalse(handle.enabled)
            self.assertIsNone(handle.probe)

    def test_is_probe_enabled_none_is_false(self):
        self.assertFalse(is_probe_enabled(None))

    def test_disabled_record_start_is_skipped(self):
        handle = ProbeHandle(config=AgentProbeConfig(enabled=False), probe=None)

        result = record_probe_start(handle)

        self.assertTrue(result.ok)
        self.assertTrue(result.skipped)
        self.assertEqual(result.event_type, "run_start")

    def test_enabled_record_start_writes_run_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(tmp, {"agent_probe_enabled": True}, env={})

            result = record_probe_start(handle, mode="video", notes="start")
            events = handle.probe.event_log.read_all()

            self.assertTrue(result.ok)
            self.assertEqual(result.event_type, "run_start")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].event_type, "run_start")

    def test_record_start_disabled_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(
                tmp,
                {
                    "agent_probe_enabled": True,
                    "agent_probe_record_start": False,
                },
                env={},
            )

            result = record_probe_start(handle)

            self.assertTrue(result.skipped)
            self.assertEqual(result.reason, "record_start disabled")
            self.assertEqual(handle.probe.event_log.read_all(), [])

    def test_enabled_record_observation_writes_observe(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(tmp, {"agent_probe_enabled": True}, env={})

            result = record_probe_observation(handle, FakeDriver(), mode="video", course_name="course")
            events = handle.probe.event_log.read_all()

            self.assertTrue(result.ok)
            self.assertEqual(result.event_type, "observe")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].event_type, "observe")
            self.assertEqual(events[0].observation.title, "\u8bfe\u7a0b\u9875\u9762")

    def test_observe_uses_fake_driver_without_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(tmp, {"agent_probe_enabled": True}, env={})

            record_probe_observation(handle, FakeDriver(), notes="fake-only")
            event = handle.probe.event_log.read_all()[0]

            self.assertEqual(event.url, "https://example.com/course")
            self.assertEqual(event.observation.notes, "fake-only")

    def test_enabled_record_legacy_action_writes_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(tmp, {"agent_probe_enabled": True}, env={})

            result = record_probe_legacy_action(
                handle,
                action_name="click_play_button",
                details={"x": 1},
            )
            events = handle.probe.event_log.read_all()

            self.assertTrue(result.ok)
            self.assertEqual(events[0].event_type, "legacy_action")

    def test_legacy_action_contains_action_name_and_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(tmp, {"agent_probe_enabled": True}, env={})

            record_probe_legacy_action(
                handle,
                action_name="click_play_button",
                details={"selector": ".play"},
            )
            event = handle.probe.event_log.read_all()[0]

            self.assertEqual(event.last_action["name"], "click_play_button")
            self.assertEqual(event.last_action["details"], {"selector": ".play"})

    def test_enabled_record_error_writes_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(tmp, {"agent_probe_enabled": True}, env={})

            result = record_probe_error(handle, Exception("boom"))
            event = handle.probe.event_log.read_all()[0]

            self.assertTrue(result.ok)
            self.assertEqual(event.event_type, "error")
            self.assertEqual(event.error, "boom")

    def test_record_error_disabled_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(
                tmp,
                {
                    "agent_probe_enabled": True,
                    "agent_probe_record_error": False,
                },
                env={},
            )

            result = record_probe_error(handle, "boom")

            self.assertTrue(result.skipped)
            self.assertEqual(result.reason, "record_error disabled")
            self.assertEqual(handle.probe.event_log.read_all(), [])

    def test_enabled_record_complete_writes_run_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(tmp, {"agent_probe_enabled": True}, env={})

            result = record_probe_complete(handle, notes="done")
            event = handle.probe.event_log.read_all()[0]

            self.assertTrue(result.ok)
            self.assertEqual(event.event_type, "run_complete")
            self.assertEqual(event.notes, "done")

    def test_record_complete_disabled_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(
                tmp,
                {
                    "agent_probe_enabled": True,
                    "agent_probe_record_complete": False,
                },
                env={},
            )

            result = record_probe_complete(handle)

            self.assertTrue(result.skipped)
            self.assertEqual(result.reason, "record_complete disabled")
            self.assertEqual(handle.probe.event_log.read_all(), [])

    def test_close_probe_handle_is_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(tmp, {"agent_probe_enabled": True}, env={})

            first = close_probe_handle(handle)
            second = close_probe_handle(handle)

            self.assertTrue(first.ok)
            self.assertTrue(second.ok)

    def test_none_or_missing_probe_records_are_safe_skipped(self):
        missing_probe = ProbeHandle(config=AgentProbeConfig(enabled=True), probe=None, enabled=True)

        for call in (
            lambda: record_probe_start(None),
            lambda: record_probe_observation(None),
            lambda: record_probe_legacy_action(None),
            lambda: record_probe_error(None, "x"),
            lambda: record_probe_complete(None),
            lambda: close_probe_handle(None),
            lambda: record_probe_start(missing_probe),
        ):
            with self.subTest(call=call):
                result = call()
                self.assertTrue(result.ok)
                self.assertTrue(result.skipped)

    def test_swallow_errors_true_returns_error_result(self):
        handle = ProbeHandle(
            config=AgentProbeConfig(enabled=True, swallow_errors=True),
            probe=FailingProbe(),
            enabled=True,
        )

        result = record_probe_start(handle)

        self.assertIsInstance(result, AdapterRecordResult)
        self.assertFalse(result.ok)
        self.assertIn("record failed", result.error)

    def test_swallow_errors_false_raises(self):
        handle = ProbeHandle(
            config=AgentProbeConfig(enabled=True, swallow_errors=False),
            probe=FailingProbe(),
            enabled=True,
        )

        with self.assertRaises(RuntimeError):
            record_probe_start(handle)

    def test_chinese_notes_write_and_read_back(self):
        note = "\u4e2d\u6587\u5907\u6ce8"
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(tmp, {"agent_probe_enabled": True}, env={})

            record_probe_complete(handle, notes=note)
            event = handle.probe.event_log.read_all()[0]

            self.assertEqual(event.notes, note)

    def test_does_not_write_screenshot_html_or_som_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            handle = create_probe_handle(tmp, {"agent_probe_enabled": True}, env={})

            record_probe_observation(handle, FakeDriver())
            files = [path.name for path in Path(tmp).rglob("*") if path.is_file()]

            self.assertTrue(any(name.endswith(".jsonl") for name in files))
            self.assertFalse(any(name.endswith(".png") for name in files))
            self.assertFalse(any(name.endswith(".html") for name in files))
            self.assertFalse(any(name.endswith(".jpg") for name in files))


if __name__ == "__main__":
    unittest.main()

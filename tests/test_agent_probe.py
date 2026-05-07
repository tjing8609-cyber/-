import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from agent.event_log import read_events  # noqa: E402
from agent.observer import AgentObserver  # noqa: E402
from agent.probe import (  # noqa: E402
    AgentProbe,
    ProbeOptions,
    ProbeRecordResult,
    create_probe,
    record_observation_once,
)
from agent.schemas import AgentEvent, ObservationFrame, StateSnapshot  # noqa: E402


class FakeDriver:
    current_url = "https://example.com/course"
    title = "课程页面"
    page_source = "<html>课程目录 章节 继续学习</html>"


class FakeObserver:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    def observe(self, *args, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("observer failed")
        return ObservationFrame.minimal(
            url="https://example.com/course",
            title="课程页面",
            mode=kwargs.get("mode", ""),
            course_name=kwargs.get("course_name", ""),
            state=kwargs.get("state") or StateSnapshot(primary_state="course_catalog"),
            notes=kwargs.get("notes", ""),
        )


class FakeEventLog:
    def __init__(self, fail_append=False):
        self.run_id = "fake-run"
        self.path = "fake.jsonl"
        self.events = []
        self.closed = False
        self.fail_append = fail_append

    def append(self, event):
        if self.fail_append:
            raise RuntimeError("append failed")
        self.events.append(event)
        return self.path

    def append_event(self, event_type, **kwargs):
        if self.fail_append:
            raise RuntimeError("append failed")
        event = AgentEvent(event_type=event_type, run_id=self.run_id, **kwargs)
        self.events.append(event)
        return event

    def summary(self):
        return {
            "run_id": self.run_id,
            "path": self.path,
            "event_count": len(self.events),
            "event_types": {event.event_type: len([x for x in self.events if x.event_type == event.event_type]) for event in self.events},
            "first_timestamp": self.events[0].timestamp if self.events else "",
            "last_timestamp": self.events[-1].timestamp if self.events else "",
            "has_error": any(event.event_type == "error" or event.error for event in self.events),
        }

    def close(self):
        self.closed = True


class AgentProbeTests(unittest.TestCase):
    def test_create_probe_returns_agent_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = create_probe(tmp, run_id="run-create")

            self.assertIsInstance(probe, AgentProbe)
            self.assertEqual(probe.run_id, "run-create")

    def test_default_constructor_has_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = AgentProbe(tmp)

            self.assertTrue(probe.run_id)

    def test_record_observation_writes_observe_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = AgentProbe(tmp, run_id="run-observe")
            result = probe.record_observation(
                FakeDriver(),
                mode="video",
                course_name="国家安全教育",
                notes="中文备注",
            )

            self.assertTrue(result.ok)
            self.assertIsInstance(result, ProbeRecordResult)
            self.assertEqual(result.event.event_type, "observe")
            self.assertEqual(result.observation.course_name, "国家安全教育")
            events = read_events(tmp, "run-observe")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].notes, "中文备注")

    def test_summary_counts_written_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = AgentProbe(tmp, run_id="run-summary")
            probe.record_observation(FakeDriver())

            summary = probe.summary()

            self.assertEqual(summary["event_count"], 1)
            self.assertEqual(summary["event_types"]["observe"], 1)
            self.assertTrue(summary["enabled"])

    def test_record_event_writes_non_observation_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = AgentProbe(tmp, run_id="run-event")
            result = probe.record_event("run_start", notes="start")

            self.assertTrue(result.ok)
            self.assertEqual(result.event.event_type, "run_start")
            self.assertEqual(read_events(tmp, "run-event")[0].notes, "start")

    def test_record_error_writes_error_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = AgentProbe(tmp, run_id="run-error")
            result = probe.record_error(Exception("x"), notes="explicit note")

            self.assertTrue(result.ok)
            self.assertEqual(result.event.event_type, "error")
            self.assertEqual(result.event.error, "x")
            self.assertEqual(result.event.notes, "explicit note")

    def test_disabled_probe_does_not_call_observer_or_log(self):
        observer = FakeObserver()
        event_log = FakeEventLog()
        probe = AgentProbe(
            project_root=".",
            observer=observer,
            event_log=event_log,
            options=ProbeOptions(enabled=False),
        )

        result = probe.record_observation(FakeDriver())

        self.assertTrue(result.ok)
        self.assertTrue(result.skipped)
        self.assertEqual(result.reason, "probe disabled")
        self.assertEqual(observer.calls, 0)
        self.assertEqual(event_log.events, [])

    def test_disabled_probe_returns_skipped_for_record_event(self):
        probe = AgentProbe(".", event_log=FakeEventLog(), options=ProbeOptions(enabled=False))

        result = probe.record_event("run_start")

        self.assertTrue(result.skipped)

    def test_auto_increment_step_index(self):
        event_log = FakeEventLog()
        probe = AgentProbe(".", observer=FakeObserver(), event_log=event_log)

        first = probe.record_observation(FakeDriver())
        second = probe.record_observation(FakeDriver())

        self.assertEqual(first.event.step_index, 0)
        self.assertEqual(second.event.step_index, 1)

    def test_explicit_step_index_takes_priority(self):
        probe = AgentProbe(".", observer=FakeObserver(), event_log=FakeEventLog())

        result = probe.record_observation(FakeDriver(), step_index=42)

        self.assertEqual(result.event.step_index, 42)

    def test_observer_error_is_swallowed_when_configured(self):
        probe = AgentProbe(".", observer=FakeObserver(fail=True), event_log=FakeEventLog())

        result = probe.record_observation(FakeDriver())

        self.assertFalse(result.ok)
        self.assertIn("observer failed", result.error)

    def test_observer_error_is_raised_when_not_swallowed(self):
        probe = AgentProbe(
            ".",
            observer=FakeObserver(fail=True),
            event_log=FakeEventLog(),
            options=ProbeOptions(swallow_errors=False),
        )

        with self.assertRaises(RuntimeError):
            probe.record_observation(FakeDriver())

    def test_event_log_append_error_is_swallowed(self):
        probe = AgentProbe(".", observer=FakeObserver(), event_log=FakeEventLog(fail_append=True))

        result = probe.record_observation(FakeDriver())

        self.assertFalse(result.ok)
        self.assertIn("append failed", result.error)

    def test_record_observation_once_records_one_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = record_observation_once(tmp, FakeDriver(), run_id="run-once", notes="once")

            self.assertTrue(result.ok)
            self.assertEqual(len(read_events(tmp, "run-once")), 1)
            self.assertEqual(read_events(tmp, "run-once")[0].notes, "once")

    def test_close_is_idempotent(self):
        event_log = FakeEventLog()
        probe = AgentProbe(".", event_log=event_log)

        probe.close()
        probe.close()

        self.assertTrue(event_log.closed)

    def test_chinese_notes_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = AgentProbe(tmp, run_id="run-cn")
            probe.record_observation(FakeDriver(), notes="中文备注")

            event = read_events(tmp, "run-cn")[0]

            self.assertEqual(event.notes, "中文备注")
            self.assertIn("中文备注", Path(tmp, "runtime", "agent_events", "run-cn.jsonl").read_text(encoding="utf-8"))

    def test_does_not_write_screenshot_html_or_som_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            screenshot = Path(tmp) / "shot.png"
            html = Path(tmp) / "page.html"
            som = Path(tmp) / "som.png"
            probe = AgentProbe(tmp, run_id="run-paths")

            result = probe.record_observation(
                FakeDriver(),
                screenshot_path=str(screenshot),
                html_snapshot_path=str(html),
                som_image_path=str(som),
            )

            self.assertTrue(result.ok)
            self.assertFalse(screenshot.exists())
            self.assertFalse(html.exists())
            self.assertFalse(som.exists())

    def test_does_not_modify_repo_runtime_when_project_root_is_temp(self):
        real_agent_events = ROOT / "runtime" / "agent_events"
        existed_before = real_agent_events.exists()
        with tempfile.TemporaryDirectory() as tmp:
            record_observation_once(tmp, FakeDriver(), run_id="run-temp")

        self.assertEqual(real_agent_events.exists(), existed_before)


if __name__ == "__main__":
    unittest.main()

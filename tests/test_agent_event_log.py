import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from agent.event_log import (  # noqa: E402
    AgentEventLog,
    ensure_event_log_dir,
    event_log_path,
    new_run_id,
    read_events,
    safe_read_jsonl,
    summarize_events,
    write_event,
)
from agent.schemas import ActionProposal, AgentEvent, StateSnapshot  # noqa: E402


class AgentEventLogTests(unittest.TestCase):
    def test_ensure_event_log_dir_creates_runtime_agent_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = ensure_event_log_dir(tmp)

            self.assertTrue(path.exists())
            self.assertTrue(path.is_dir())
            self.assertEqual(path.name, "agent_events")
            self.assertEqual(path.parent.name, "runtime")

    def test_new_run_id_has_prefix(self):
        run_id = new_run_id("case")

        self.assertTrue(run_id)
        self.assertTrue(run_id.startswith("case_"))
        self.assertGreaterEqual(len(run_id.split("_")), 4)

    def test_event_log_path_returns_jsonl_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = event_log_path(tmp, "run-1")

            self.assertEqual(path.suffix, ".jsonl")
            self.assertEqual(path.name, "run-1.jsonl")
            self.assertTrue(path.parent.exists())

    def test_append_writes_one_agent_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = AgentEventLog(tmp, run_id="run-append")
            path = log.append(AgentEvent(event_type="run_start", notes="开始"))

            self.assertTrue(path.exists())
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            data = json.loads(lines[0])
            self.assertEqual(data["event_type"], "run_start")
            self.assertEqual(data["run_id"], "run-append")

    def test_read_all_restores_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = AgentEventLog(tmp, run_id="run-read")
            log.append(AgentEvent(event_type="run_start"))
            log.append(AgentEvent(event_type="observe", state=StateSnapshot(primary_state="video_page")))

            events = log.read_all()

            self.assertEqual([event.event_type for event in events], ["run_start", "observe"])
            self.assertEqual(events[1].state.primary_state, "video_page")

    def test_append_event_creates_and_writes_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = AgentEventLog(tmp, run_id="run-fast")
            event = log.append_event(
                "proposal",
                step_index=2,
                mode="video",
                proposal=ActionProposal.noop("observe only"),
                notes="快速写入",
            )

            self.assertEqual(event.event_type, "proposal")
            self.assertEqual(event.run_id, "run-fast")
            restored = log.read_all()[0]
            self.assertEqual(restored.proposal.action_type, "noop")
            self.assertEqual(restored.notes, "快速写入")

    def test_iter_events_filters_by_event_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = AgentEventLog(tmp, run_id="run-filter")
            log.append_event("run_start")
            log.append_event("observe", step_index=1)
            log.append_event("observe", step_index=2)
            log.append_event("proposal", step_index=3)

            observed = list(log.iter_events(event_type="observe"))

            self.assertEqual(len(observed), 2)
            self.assertEqual([event.step_index for event in observed], [1, 2])

    def test_summary_counts_event_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = AgentEventLog(tmp, run_id="run-summary")
            log.append_event("run_start")
            log.append_event("observe")
            log.append_event("observe")
            log.append_event("error", error="boom")

            summary = log.summary()

            self.assertEqual(summary["run_id"], "run-summary")
            self.assertEqual(summary["event_count"], 4)
            self.assertEqual(summary["event_types"]["observe"], 2)
            self.assertTrue(summary["has_error"])
            self.assertTrue(summary["path"].endswith("run-summary.jsonl"))

    def test_safe_read_jsonl_missing_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.jsonl"

            self.assertEqual(safe_read_jsonl(missing), [])

    def test_safe_read_jsonl_skips_damaged_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            first = AgentEvent(event_type="run_start", run_id="run-damaged").to_json_line()
            second = AgentEvent(event_type="observe", run_id="run-damaged").to_json_line()
            path.write_text(first + "not-json\n" + second, encoding="utf-8")

            events = safe_read_jsonl(path)

            self.assertEqual([event.event_type for event in events], ["run_start", "observe"])

    def test_close_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = AgentEventLog(tmp, run_id="run-close")

            log.close()
            log.close()

            self.assertTrue(log.closed)

    def test_chinese_notes_round_trip_without_forced_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = AgentEventLog(tmp, run_id="run-cn")
            log.append_event("observe", notes="中文备注")

            raw = log.path.read_text(encoding="utf-8")
            restored = log.read_all()[0]

            self.assertIn("中文备注", raw)
            self.assertNotIn("\\u4e2d", raw)
            self.assertEqual(restored.notes, "中文备注")

    def test_convenience_write_read_and_summarize(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_event(tmp, "run-helper", AgentEvent(event_type="run_start"))
            write_event(tmp, "run-helper", AgentEvent(event_type="run_complete"))

            events = read_events(tmp, "run-helper")
            summary = summarize_events(events)

            self.assertEqual(len(events), 2)
            self.assertEqual(summary["event_count"], 2)
            self.assertEqual(summary["event_types"]["run_complete"], 1)


if __name__ == "__main__":
    unittest.main()

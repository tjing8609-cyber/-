import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from agent.event_log import AgentEventLog  # noqa: E402
from agent.replay import (  # noqa: E402
    ReplaySummary,
    event_to_digest,
    format_replay_markdown,
    load_replay,
    load_replay_from_file,
    replay_to_dict,
    summarize_replay,
)
from agent.schemas import AgentEvent, ObservationFrame, StateSnapshot  # noqa: E402


def make_observation(page_text_digest="\u8bfe\u7a0b\u76ee\u5f55 \u7ee7\u7eed\u5b66\u4e60"):
    return ObservationFrame(
        url="https://example.com/course",
        title="\u8bfe\u7a0b\u9875\u9762",
        mode="video",
        course_name="\u56fd\u5bb6\u5b89\u5168\u6559\u80b2",
        state=StateSnapshot(
            primary_state="course_catalog",
            overlays=["common_dialog"],
            task_phase="navigate_course",
            confidence=0.8,
        ),
        page_text_digest=page_text_digest,
        notes="\u4e2d\u6587\u5907\u6ce8",
    )


def make_events(run_id="run-1"):
    return [
        AgentEvent(event_type="run_start", run_id=run_id, step_index=0, mode="video", notes="start"),
        AgentEvent(
            event_type="observe",
            run_id=run_id,
            step_index=1,
            mode="video",
            observation=make_observation(),
            notes="lifecycle=run_complete",
        ),
        AgentEvent(event_type="run_complete", run_id=run_id, step_index=2, mode="video", notes="done"),
    ]


class AgentReplayTests(unittest.TestCase):
    def test_event_to_digest_handles_run_start(self):
        event = AgentEvent(event_type="run_start", run_id="run-1", step_index=3, mode="video", notes="start")

        digest = event_to_digest(event)

        self.assertEqual(digest["event_type"], "run_start")
        self.assertEqual(digest["step_index"], 3)
        self.assertEqual(digest["mode"], "video")
        self.assertEqual(digest["notes"], "start")

    def test_event_to_digest_handles_observe_with_observation(self):
        event = AgentEvent(event_type="observe", run_id="run-1", observation=make_observation())

        digest = event_to_digest(event)

        self.assertEqual(digest["observation_url"], "https://example.com/course")
        self.assertEqual(digest["observation_title"], "\u8bfe\u7a0b\u9875\u9762")
        self.assertEqual(digest["primary_state"], "course_catalog")
        self.assertIn("common_dialog", digest["overlays"])

    def test_page_text_digest_is_truncated(self):
        long_digest = "x" * 500
        event = AgentEvent(event_type="observe", observation=make_observation(long_digest))

        digest = event_to_digest(event)

        self.assertEqual(len(digest["page_text_digest"]), 300)

    def test_summarize_empty_returns_empty_summary(self):
        summary = summarize_replay([])

        self.assertIsInstance(summary, ReplaySummary)
        self.assertEqual(summary.event_count, 0)
        self.assertFalse(summary.completed)

    def test_summarize_counts_event_types(self):
        summary = summarize_replay(make_events())

        self.assertEqual(summary.event_count, 3)
        self.assertEqual(summary.event_types["run_start"], 1)
        self.assertEqual(summary.event_types["observe"], 1)

    def test_summarize_detects_completed(self):
        summary = summarize_replay(make_events())

        self.assertTrue(summary.completed)
        self.assertEqual(summary.complete_event["event_type"], "run_complete")

    def test_summarize_detects_has_error(self):
        events = make_events()[:2] + [AgentEvent(event_type="error", run_id="run-1", error="boom")]

        summary = summarize_replay(events)

        self.assertTrue(summary.has_error)
        self.assertEqual(summary.error_events[0]["error"], "boom")

    def test_summarize_builds_url_timeline(self):
        summary = summarize_replay(make_events())

        self.assertEqual(summary.url_timeline[0]["url"], "https://example.com/course")

    def test_summarize_builds_state_timeline(self):
        summary = summarize_replay(make_events())

        states = [item["primary_state"] for item in summary.state_timeline]
        self.assertIn("course_catalog", states)

    def test_load_replay_from_missing_file_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.jsonl"

            summary = load_replay_from_file(path)

            self.assertEqual(summary.event_count, 0)

    def test_load_replay_from_file_reads_valid_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = AgentEventLog(tmp, run_id="valid")
            for event in make_events("valid"):
                log.append(event)

            summary = load_replay_from_file(log.path)

            self.assertEqual(summary.run_id, "valid")
            self.assertEqual(summary.event_count, 3)

    def test_load_replay_reads_project_root_and_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = AgentEventLog(tmp, run_id="project-run")
            log.append(make_events("project-run")[0])

            summary = load_replay(tmp, "project-run")

            self.assertEqual(summary.run_id, "project-run")
            self.assertEqual(summary.event_count, 1)

    def test_format_markdown_empty_summary(self):
        markdown = format_replay_markdown(ReplaySummary())

        self.assertIn("Agent Replay Summary", markdown)
        self.assertIn("No events recorded", markdown)

    def test_format_markdown_contains_event_types(self):
        markdown = format_replay_markdown(summarize_replay(make_events()))

        self.assertIn("## Event Types", markdown)
        self.assertIn("run_start", markdown)

    def test_format_markdown_contains_url_timeline(self):
        markdown = format_replay_markdown(summarize_replay(make_events()))

        self.assertIn("## URL Timeline", markdown)
        self.assertIn("https://example.com/course", markdown)

    def test_chinese_title_notes_digest_are_preserved(self):
        summary = summarize_replay(make_events())
        data = summary.to_dict()
        markdown = format_replay_markdown(summary)

        self.assertEqual(data["observe_events"][0]["observation_title"], "\u8bfe\u7a0b\u9875\u9762")
        self.assertIn("\u8bfe\u7a0b\u76ee\u5f55", data["observe_events"][0]["page_text_digest"])
        self.assertIn("\u8bfe\u7a0b\u9875\u9762", markdown)

    def test_corrupt_jsonl_lines_do_not_crash_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = AgentEventLog(tmp, run_id="corrupt")
            log.append(make_events("corrupt")[0])
            with Path(log.path).open("a", encoding="utf-8") as handle:
                handle.write("{bad json\n")
                handle.write(json.dumps(make_events("corrupt")[1].to_dict(), ensure_ascii=False) + "\n")

            summary = load_replay_from_file(log.path)

            self.assertEqual(summary.event_count, 2)
            self.assertEqual(summary.event_types["run_start"], 1)
            self.assertEqual(summary.event_types["observe"], 1)

    def test_replay_does_not_write_extra_runtime_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_path = root / "missing.jsonl"
            before = sorted(path.relative_to(root) for path in root.rglob("*"))

            load_replay_from_file(missing_path)
            load_replay(root, "missing-run")
            replay_to_dict(root, "missing-run")

            after = sorted(path.relative_to(root) for path in root.rglob("*"))
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()

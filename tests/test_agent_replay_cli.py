import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from agent.event_log import AgentEventLog  # noqa: E402
from agent.replay import summarize_replay  # noqa: E402
from agent.schemas import AgentEvent, ObservationFrame, StateSnapshot  # noqa: E402


def load_tool_module():
    script = ROOT / "tools" / "agent_replay.py"
    spec = importlib.util.spec_from_file_location("agent_replay_tool", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent_replay = load_tool_module()


def make_event(run_id="run-1", title="\u8bfe\u7a0b\u9875\u9762", notes="\u4e2d\u6587\u5907\u6ce8", digest="\u8bfe\u7a0b\u76ee\u5f55"):
    observation = ObservationFrame(
        url=f"https://example.com/{run_id}",
        title=title,
        mode="video",
        course_name="\u56fd\u5bb6\u5b89\u5168\u6559\u80b2",
        state=StateSnapshot(primary_state="course_catalog", task_phase="navigate_course"),
        page_text_digest=digest,
    )
    return AgentEvent(
        event_type="observe",
        run_id=run_id,
        step_index=1,
        mode="video",
        observation=observation,
        notes=notes,
    )


def write_log(project_root, run_id, event=None):
    log = AgentEventLog(project_root, run_id=run_id)
    log.append(AgentEvent(event_type="run_start", run_id=run_id, step_index=0, notes="start"))
    log.append(event or make_event(run_id=run_id))
    return Path(log.path)


def run_cli(args):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = agent_replay.run_cli(args)
    return code, stdout.getvalue(), stderr.getvalue()


class AgentReplayCliTests(unittest.TestCase):
    def test_agent_events_dir_returns_expected_path(self):
        root = Path("project")

        self.assertEqual(agent_replay.agent_events_dir(root), root / "runtime" / "agent_events")

    def test_find_latest_missing_directory_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(agent_replay.find_latest_event_log(tmp))

    def test_find_latest_event_log_finds_newest_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = write_log(tmp, "old")
            new_path = write_log(tmp, "new")
            os.utime(old_path, (100, 100))
            os.utime(new_path, (200, 200))

            self.assertEqual(agent_replay.find_latest_event_log(tmp), new_path)

    def test_list_event_logs_sorts_by_mtime_desc(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = write_log(tmp, "first")
            second = write_log(tmp, "second")
            os.utime(first, (100, 100))
            os.utime(second, (300, 300))

            items = agent_replay.list_event_logs(tmp)

            self.assertEqual([item["name"] for item in items], ["second.jsonl", "first.jsonl"])

    def test_format_event_log_list_empty_is_friendly(self):
        self.assertIn("No agent event logs found", agent_replay.format_event_log_list([]))

    def test_summary_to_json_preserves_chinese(self):
        summary = summarize_replay([make_event()])

        text = agent_replay.summary_to_json(summary)

        self.assertIn("\u8bfe\u7a0b\u9875\u9762", text)
        self.assertNotIn("\\u8bfe", text)

    def test_run_cli_list_missing_directory_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, stderr = run_cli(["--project-root", tmp, "--list"])

            self.assertEqual(code, 0)
            self.assertIn("No agent event logs found", stdout)
            self.assertEqual(stderr, "")

    def test_run_cli_latest_without_logs_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, stderr = run_cli(["--project-root", tmp, "--latest"])

            self.assertEqual(code, 1)
            self.assertEqual(stdout, "")
            self.assertIn("No agent event logs found", stderr)

    def test_run_cli_run_id_missing_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, stderr = run_cli(["--project-root", tmp, "--run-id", "abc"])

            self.assertEqual(code, 1)
            self.assertEqual(stdout, "")
            self.assertIn("not found", stderr)

    def test_run_cli_file_outputs_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_log(tmp, "markdown")

            code, stdout, stderr = run_cli(["--file", str(path)])

            self.assertEqual(code, 0)
            self.assertIn("# Agent Replay Summary", stdout)
            self.assertIn("## Event Types", stdout)
            self.assertEqual(stderr, "")

    def test_run_cli_file_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_log(tmp, "json-run")

            code, stdout, stderr = run_cli(["--file", str(path), "--format", "json"])
            data = json.loads(stdout)

            self.assertEqual(code, 0)
            self.assertEqual(data["run_id"], "json-run")
            self.assertEqual(stderr, "")

    def test_file_takes_priority_over_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = write_log(tmp, "file-run", make_event(run_id="file-run", title="file-title"))
            write_log(tmp, "run-id", make_event(run_id="run-id", title="run-title"))

            code, stdout, _stderr = run_cli(
                [
                    "--project-root",
                    tmp,
                    "--file",
                    str(file_path),
                    "--run-id",
                    "run-id",
                    "--format",
                    "json",
                ]
            )
            data = json.loads(stdout)

            self.assertEqual(code, 0)
            self.assertEqual(data["observe_events"][0]["observation_title"], "file-title")

    def test_run_id_reads_from_project_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_log(tmp, "by-run-id")

            code, stdout, stderr = run_cli(["--project-root", tmp, "--run-id", "by-run-id"])

            self.assertEqual(code, 0)
            self.assertIn("by-run-id", stdout)
            self.assertEqual(stderr, "")

    def test_latest_reads_newest_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = write_log(tmp, "old-latest", make_event(run_id="old-latest", title="old-title"))
            new_path = write_log(tmp, "new-latest", make_event(run_id="new-latest", title="new-title"))
            os.utime(old_path, (100, 100))
            os.utime(new_path, (400, 400))

            code, stdout, stderr = run_cli(["--project-root", tmp, "--latest", "--format", "json"])
            data = json.loads(stdout)

            self.assertEqual(code, 0)
            self.assertEqual(data["run_id"], "new-latest")
            self.assertIn("new-title", stdout)
            self.assertEqual(stderr, "")

    def test_missing_target_returns_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, stderr = run_cli(["--project-root", tmp])

            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("usage:", stderr)

    def test_corrupt_jsonl_line_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_log(tmp, "corrupt")
            with path.open("a", encoding="utf-8") as handle:
                handle.write("{bad json\n")

            code, stdout, stderr = run_cli(["--file", str(path)])

            self.assertEqual(code, 0)
            self.assertIn("Agent Replay Summary", stdout)
            self.assertEqual(stderr, "")

    def test_chinese_content_can_be_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_log(tmp, "cn")

            code, stdout, _stderr = run_cli(["--file", str(path)])

            self.assertEqual(code, 0)
            self.assertIn("\u8bfe\u7a0b\u9875\u9762", stdout)
            self.assertIn("\u4e2d\u6587\u5907\u6ce8", stdout)

    def test_cli_does_not_create_extra_runtime_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = sorted(path.relative_to(root) for path in root.rglob("*"))

            run_cli(["--project-root", tmp, "--list"])
            run_cli(["--project-root", tmp, "--latest"])
            run_cli(["--project-root", tmp, "--run-id", "missing"])

            after = sorted(path.relative_to(root) for path in root.rglob("*"))
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()

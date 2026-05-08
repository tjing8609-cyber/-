import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

import player_runner  # noqa: E402
from agent.event_log import read_events  # noqa: E402


class FakeTarget:
    module_name = "fake_player_module"
    class_name = "FakePlayer"


class FakeDriver:
    current_url = "https://example.com/course"
    title = "\u8bfe\u7a0b\u9875\u9762"
    page_source = "<html><body>\u8bfe\u7a0b\u76ee\u5f55 \u7ee7\u7eed\u5b66\u4e60</body></html>"


class FakePlayer:
    def __init__(self, driver=None, fail=False):
        self.driver = driver
        self.fail = fail

    def run(self):
        if self.fail:
            raise RuntimeError("boom")


class NoDriverPlayer:
    def run(self):
        return None


class BrokenDriverPlayer:
    @property
    def driver(self):
        raise RuntimeError("driver unavailable")

    def run(self):
        return None


class CountingDriverPlayer:
    def __init__(self):
        self.driver_reads = 0

    @property
    def driver(self):
        self.driver_reads += 1
        return FakeDriver()

    def run(self):
        return None


class FakeContext:
    def __init__(
        self,
        project_root,
        *,
        run_id="observation_run",
        enabled=True,
        account_path=None,
        mode="video",
        course_name="\u56fd\u5bb6\u5b89\u5168\u6559\u80b2",
    ):
        self.project_root = Path(project_root)
        self.account_path = Path(account_path or self.project_root / "account.json")
        self.mode = mode
        self.course_name = course_name
        self.config = {
            "agent_probe_enabled": enabled,
            "agent_probe_run_id": run_id,
            "mode": mode,
            "course_name": course_name,
        }
        self.headless = False

    @property
    def normalized_config(self):
        return dict(self.config)


class PlayerRunnerProbeObservationTests(unittest.TestCase):
    def _execute(self, context, player, snapshot_calls=None):
        if snapshot_calls is None:
            snapshot_calls = []

        def write_failure_snapshot(*args):
            snapshot_calls.append(args)
            return "snapshot.json"

        with patch.object(player_runner, "create_player", return_value=player):
            player_runner.execute_player(FakeTarget(), context, lambda *args: None, write_failure_snapshot)

    def _execute_raising(self, context, player, snapshot_calls=None):
        if snapshot_calls is None:
            snapshot_calls = []

        def write_failure_snapshot(*args):
            snapshot_calls.append(args)
            return "snapshot.json"

        with patch.object(player_runner, "create_player", return_value=player):
            with self.assertRaises(RuntimeError):
                player_runner.execute_player(FakeTarget(), context, lambda *args: None, write_failure_snapshot)

    def test_enabled_completion_event_order_includes_observe(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, run_id="complete_order")

            self._execute(context, FakePlayer(driver=FakeDriver()))
            events = read_events(tmp, "complete_order")

            self.assertEqual([event.event_type for event in events], ["run_start", "observe", "run_complete"])

    def test_completion_observe_contains_fake_driver_url_title_and_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, run_id="complete_fields")

            self._execute(context, FakePlayer(driver=FakeDriver()))
            observe = read_events(tmp, "complete_fields")[1]

            self.assertEqual(observe.observation.url, "https://example.com/course")
            self.assertEqual(observe.observation.title, "\u8bfe\u7a0b\u9875\u9762")
            self.assertIn("\u8bfe\u7a0b\u76ee\u5f55", observe.observation.page_text_digest)
            self.assertEqual(observe.observation.mode, "video")
            self.assertEqual(observe.observation.course_name, "\u56fd\u5bb6\u5b89\u5168\u6559\u80b2")
            self.assertIsNotNone(observe.observation.state)

    def test_completion_observe_notes_mark_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, run_id="complete_notes")

            self._execute(context, FakePlayer(driver=FakeDriver()))
            observe = read_events(tmp, "complete_notes")[1]

            self.assertIn("lifecycle=run_complete", observe.notes)

    def test_enabled_exception_event_order_includes_observe(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, run_id="error_order")

            self._execute_raising(context, FakePlayer(driver=FakeDriver(), fail=True))
            events = read_events(tmp, "error_order")

            self.assertEqual([event.event_type for event in events], ["run_start", "observe", "error"])

    def test_exception_observe_notes_mark_lifecycle_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, run_id="error_notes")

            self._execute_raising(context, FakePlayer(driver=FakeDriver(), fail=True))
            observe = read_events(tmp, "error_notes")[1]

            self.assertIn("lifecycle=error", observe.notes)

    def test_regular_exception_still_propagates(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, run_id="error_propagates")

            with patch.object(player_runner, "create_player", return_value=FakePlayer(driver=FakeDriver(), fail=True)):
                with self.assertRaises(RuntimeError):
                    player_runner.execute_player(FakeTarget(), context, lambda *args: None, lambda *args: "snapshot")

    def test_regular_exception_still_calls_failure_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, run_id="error_snapshot")
            snapshot_calls = []

            self._execute_raising(context, FakePlayer(driver=FakeDriver(), fail=True), snapshot_calls)

            self.assertEqual(len(snapshot_calls), 1)

    def test_player_import_error_does_not_write_observe(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, run_id="import_error")
            error = player_runner.PlayerImportError(FakeTarget(), ImportError("missing"))

            with patch.object(player_runner, "create_player", side_effect=error):
                with self.assertRaises(player_runner.PlayerImportError):
                    player_runner.execute_player(FakeTarget(), context, lambda *args: None, lambda *args: "snapshot")

            self.assertEqual([event.event_type for event in read_events(tmp, "import_error")], ["run_start", "error"])

    def test_no_driver_skips_observe_but_writes_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, run_id="no_driver")

            self._execute(context, NoDriverPlayer())

            self.assertEqual([event.event_type for event in read_events(tmp, "no_driver")], ["run_start", "run_complete"])

    def test_driver_read_error_skips_observe_without_affecting_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, run_id="broken_driver")

            self._execute(context, BrokenDriverPlayer())

            self.assertEqual([event.event_type for event in read_events(tmp, "broken_driver")], ["run_start", "run_complete"])

    def test_disabled_does_not_create_runtime_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, run_id="disabled", enabled=False)

            self._execute(context, FakePlayer(driver=FakeDriver()))

            self.assertFalse((Path(tmp) / "runtime" / "agent_events").exists())

    def test_disabled_does_not_read_player_driver(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, run_id="disabled_no_read", enabled=False)
            player = CountingDriverPlayer()

            self._execute(context, player)

            self.assertEqual(player.driver_reads, 0)

    def test_observation_writes_no_screenshot_html_or_som_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, run_id="no_artifacts")

            self._execute(context, FakePlayer(driver=FakeDriver()))
            observe = read_events(tmp, "no_artifacts")[1]

            self.assertEqual(observe.observation.screenshot_path, "")
            self.assertEqual(observe.observation.html_snapshot_path, "")
            self.assertEqual(observe.observation.som_image_path, "")


if __name__ == "__main__":
    unittest.main()

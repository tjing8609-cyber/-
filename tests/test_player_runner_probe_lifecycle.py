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


class FakeContext:
    def __init__(
        self,
        project_root,
        *,
        account_path=None,
        mode="video",
        config=None,
        normalized_config=None,
        headless=False,
    ):
        self.project_root = Path(project_root)
        self.account_path = Path(account_path or self.project_root / "account.json")
        self.mode = mode
        self.config = config or {}
        self._normalized_config = normalized_config
        self.headless = headless

    @property
    def normalized_config(self):
        if isinstance(self._normalized_config, Exception):
            raise self._normalized_config
        if self._normalized_config is not None:
            return self._normalized_config
        return dict(self.config)


class FakePlayer:
    def __init__(self, fail=False):
        self.fail = fail
        self.ran = False

    def run(self):
        self.ran = True
        if self.fail:
            raise RuntimeError("run failed")


class PlayerRunnerProbeLifecycleTests(unittest.TestCase):
    def _updates(self):
        updates = []

        def update_observability(_root, payload):
            updates.append(payload)

        return updates, update_observability

    def _snapshot(self):
        calls = []

        def write_failure_snapshot(*args):
            calls.append(args)
            return "snapshot.json"

        return calls, write_failure_snapshot

    def _event_types(self, project_root, run_id):
        return [event.event_type for event in read_events(project_root, run_id)]

    def test_default_disabled_executes_without_runtime_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, normalized_config={})
            updates, update = self._updates()
            snapshots, snapshot = self._snapshot()

            with patch.object(player_runner, "create_player", return_value=FakePlayer()):
                player_runner.execute_player(FakeTarget(), context, update, snapshot)

            self.assertEqual([item["status"] for item in updates], ["running", "completed"])
            self.assertEqual(snapshots, [])
            self.assertFalse((Path(tmp) / "runtime" / "agent_events").exists())

    def test_enabled_normal_completion_writes_start_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "normal_run"
            context = FakeContext(
                tmp,
                normalized_config={
                    "agent_probe_enabled": True,
                    "agent_probe_run_id": run_id,
                },
            )
            updates, update = self._updates()

            with patch.object(player_runner, "create_player", return_value=FakePlayer()):
                player_runner.execute_player(FakeTarget(), context, update, lambda *args: "snapshot")

            self.assertEqual(self._event_types(tmp, run_id), ["run_start", "run_complete"])
            self.assertEqual([item["status"] for item in updates], ["running", "completed"])

    def test_enabled_run_exception_writes_start_and_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "run_error"
            context = FakeContext(
                tmp,
                normalized_config={
                    "agent_probe_enabled": True,
                    "agent_probe_run_id": run_id,
                },
            )
            updates, update = self._updates()
            snapshots, snapshot = self._snapshot()

            with patch.object(player_runner, "create_player", return_value=FakePlayer(fail=True)):
                with self.assertRaises(RuntimeError):
                    player_runner.execute_player(FakeTarget(), context, update, snapshot)

            events = read_events(tmp, run_id)
            self.assertEqual([event.event_type for event in events], ["run_start", "error"])
            self.assertEqual(events[-1].error, "run failed")
            self.assertEqual([item["status"] for item in updates], ["running", "failed"])
            self.assertEqual(len(snapshots), 1)

    def test_enabled_import_error_writes_start_and_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "import_error"
            context = FakeContext(
                tmp,
                normalized_config={
                    "agent_probe_enabled": True,
                    "agent_probe_run_id": run_id,
                },
            )
            updates, update = self._updates()
            error = player_runner.PlayerImportError(FakeTarget(), ImportError("missing module"))

            with patch.object(player_runner, "create_player", side_effect=error):
                with self.assertRaises(player_runner.PlayerImportError):
                    player_runner.execute_player(FakeTarget(), context, update, lambda *args: "snapshot")

            events = read_events(tmp, run_id)
            self.assertEqual([event.event_type for event in events], ["run_start", "error"])
            self.assertEqual(events[-1].error, "missing module")
            self.assertEqual([item["status"] for item in updates], ["import_error"])

    def test_regular_exception_still_propagates(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, normalized_config={"agent_probe_enabled": True})
            updates, update = self._updates()

            with patch.object(player_runner, "create_player", return_value=FakePlayer(fail=True)):
                with self.assertRaises(RuntimeError):
                    player_runner.execute_player(FakeTarget(), context, update, lambda *args: "snapshot")

    def test_player_import_error_still_propagates(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, normalized_config={"agent_probe_enabled": True})
            error = player_runner.PlayerImportError(FakeTarget(), ImportError("missing"))

            with patch.object(player_runner, "create_player", side_effect=error):
                with self.assertRaises(player_runner.PlayerImportError):
                    player_runner.execute_player(FakeTarget(), context, lambda *args: None, lambda *args: "snapshot")

    def test_observability_statuses_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = FakeTarget()

            normal_updates, normal_update = self._updates()
            normal_context = FakeContext(
                tmp,
                normalized_config={"agent_probe_enabled": True, "agent_probe_run_id": "obs_normal"},
            )
            with patch.object(player_runner, "create_player", return_value=FakePlayer()):
                player_runner.execute_player(target, normal_context, normal_update, lambda *args: "snapshot")
            self.assertEqual([item["status"] for item in normal_updates], ["running", "completed"])

            failed_updates, failed_update = self._updates()
            failed_context = FakeContext(
                tmp,
                normalized_config={"agent_probe_enabled": True, "agent_probe_run_id": "obs_failed"},
            )
            with patch.object(player_runner, "create_player", return_value=FakePlayer(fail=True)):
                with self.assertRaises(RuntimeError):
                    player_runner.execute_player(target, failed_context, failed_update, lambda *args: "snapshot")
            self.assertEqual([item["status"] for item in failed_updates], ["running", "failed"])

            import_updates, import_update = self._updates()
            import_context = FakeContext(
                tmp,
                normalized_config={"agent_probe_enabled": True, "agent_probe_run_id": "obs_import"},
            )
            error = player_runner.PlayerImportError(target, ImportError("missing"))
            with patch.object(player_runner, "create_player", side_effect=error):
                with self.assertRaises(player_runner.PlayerImportError):
                    player_runner.execute_player(target, import_context, import_update, lambda *args: "snapshot")
            self.assertEqual([item["status"] for item in import_updates], ["import_error"])

    def test_regular_exception_still_calls_failure_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, normalized_config={"agent_probe_enabled": True})
            snapshots, snapshot = self._snapshot()

            with patch.object(player_runner, "create_player", return_value=FakePlayer(fail=True)):
                with self.assertRaises(RuntimeError):
                    player_runner.execute_player(FakeTarget(), context, lambda *args: None, snapshot)

            self.assertEqual(len(snapshots), 1)
            self.assertEqual(snapshots[0][2], "fake_player_module")

    def test_probe_disabled_does_not_write_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(tmp, normalized_config={"agent_probe_enabled": False})

            with patch.object(player_runner, "create_player", return_value=FakePlayer()):
                player_runner.execute_player(FakeTarget(), context, lambda *args: None, lambda *args: "snapshot")

            self.assertFalse((Path(tmp) / "runtime" / "agent_events").exists())

    def test_chinese_account_path_is_readable_from_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "\u4e2d\u6587_run"
            account_path = Path(tmp) / "\u542f\u52a8" / "\u8d26\u53f7.json"
            context = FakeContext(
                tmp,
                account_path=account_path,
                normalized_config={
                    "agent_probe_enabled": True,
                    "agent_probe_run_id": run_id,
                },
            )

            with patch.object(player_runner, "create_player", return_value=FakePlayer()):
                player_runner.execute_player(FakeTarget(), context, lambda *args: None, lambda *args: "snapshot")

            events = read_events(tmp, run_id)
            self.assertIn("\u8d26\u53f7.json", events[0].account_file)

    def test_close_probe_handle_is_called_without_affecting_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(
                tmp,
                normalized_config={
                    "agent_probe_enabled": True,
                    "agent_probe_run_id": "close_run",
                },
            )
            close_calls = []
            real_close = player_runner.close_probe_handle

            def close_spy(handle):
                close_calls.append(handle)
                return real_close(handle)

            with patch.object(player_runner, "create_player", return_value=FakePlayer()):
                with patch.object(player_runner, "close_probe_handle", side_effect=close_spy):
                    player_runner.execute_player(FakeTarget(), context, lambda *args: None, lambda *args: "snapshot")

            self.assertEqual(len(close_calls), 1)
            self.assertEqual(self._event_types(tmp, "close_run"), ["run_start", "run_complete"])

    def test_probe_record_failure_does_not_interrupt_player(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeContext(
                tmp,
                normalized_config={
                    "agent_probe_enabled": True,
                    "agent_probe_run_id": "probe_failure",
                    "agent_probe_swallow_errors": False,
                },
            )
            updates, update = self._updates()

            with patch.object(player_runner, "create_player", return_value=FakePlayer()):
                with patch.object(player_runner, "record_probe_start", side_effect=RuntimeError("probe start failed")):
                    with patch.object(
                        player_runner,
                        "record_probe_complete",
                        side_effect=RuntimeError("probe complete failed"),
                    ):
                        with patch.object(
                            player_runner,
                            "close_probe_handle",
                            side_effect=RuntimeError("probe close failed"),
                        ):
                            player_runner.execute_player(FakeTarget(), context, update, lambda *args: "snapshot")

            self.assertEqual([item["status"] for item in updates], ["running", "completed"])


if __name__ == "__main__":
    unittest.main()

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from player_runner import create_player, execute_player, observability_payload  # noqa: E402
from run_context import create_run_context  # noqa: E402
from run_target import RunTarget  # noqa: E402


class FakePlayer:
    instances = []

    def __init__(self, account_file, headless):
        self.account_file = account_file
        self.headless = headless
        self.ran = False
        FakePlayer.instances.append(self)

    def run(self):
        self.ran = True


class PlayerRunnerTests(unittest.TestCase):
    def setUp(self):
        FakePlayer.instances = []
        module = types.ModuleType("fake_player_module")
        module.FakePlayer = FakePlayer
        sys.modules["fake_player_module"] = module

    def tearDown(self):
        sys.modules.pop("fake_player_module", None)

    def _target(self):
        return RunTarget(
            detect_message="detect",
            module_name="fake_player_module",
            class_name="FakePlayer",
            start_message="start",
            import_error_message="import {error}",
            missing_file_message="missing",
        )

    def test_create_player_uses_context_account_path(self):
        context = create_run_context(
            "account.json",
            headless=True,
            code_dir=CODE_DIR,
            account_config={"mode": "video", "course_type": 1},
        )

        player = create_player(self._target(), context)

        self.assertTrue(player.headless)
        self.assertIn("account.json", player.account_file)

    def test_execute_player_updates_running_and_completed(self):
        context = create_run_context(
            "account.json",
            code_dir=CODE_DIR,
            account_config={"mode": "video", "course_type": 1},
        )
        updates = []

        execute_player(
            self._target(),
            context,
            update_observability=lambda root, payload: updates.append(payload["status"]),
            write_failure_snapshot=lambda *args: "snapshot",
        )

        self.assertEqual(updates, ["running", "completed"])
        self.assertTrue(FakePlayer.instances[0].ran)

    def test_observability_payload_shape(self):
        context = create_run_context(
            "account.json",
            code_dir=CODE_DIR,
            account_config={"mode": "quiz_only"},
        )
        payload = observability_payload("running", context, self._target(), extra="x")

        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["module"], "fake_player_module")
        self.assertEqual(payload["extra"], "x")


if __name__ == "__main__":
    unittest.main()

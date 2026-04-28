import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from run_target import resolve_run_target  # noqa: E402


class RunTargetTests(unittest.TestCase):
    def test_video_course_type_accepts_numeric_string(self):
        target = resolve_run_target("video", "2")

        self.assertEqual(target.module_name, "zhidao_web_auto_player_with_quiz")
        self.assertEqual(target.type_message, "[类型] 2")

    def test_course_type_three_routes_to_quiz_only(self):
        target = resolve_run_target("video", 3)

        self.assertEqual(target.module_name, "zhidao_quiz_only_player")
        self.assertIn("mode='quiz_only'", target.extra_messages[0])

    def test_unknown_combo_returns_none(self):
        self.assertIsNone(resolve_run_target("video", "bad"))

    def test_legacy_dict_shape(self):
        target = resolve_run_target("quiz_only", 1).as_legacy_dict()

        self.assertEqual(target["module_name"], "zhidao_quiz_only_player")
        self.assertIn("detect_message", target)


if __name__ == "__main__":
    unittest.main()

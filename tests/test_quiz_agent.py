import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from quiz_agent import QuizAutomationAgent, normalize_answer_mode, normalize_letters  # noqa: E402


class QuizAgentTests(unittest.TestCase):
    def test_mode_aliases(self):
        self.assertEqual(normalize_answer_mode("auto"), "auto_practice")
        self.assertEqual(normalize_answer_mode("semi"), "semi_auto")
        self.assertEqual(normalize_answer_mode("bad", default="assist"), "assist")

    def test_normalize_letters_filters_invalid_options(self):
        self.assertEqual(normalize_letters(["A", "E", "B", "A"], 3), ["A", "B"])

    def test_assist_mode_does_not_click(self):
        decision = QuizAutomationAgent("assist").decide(["A"], option_count=4)

        self.assertFalse(decision.should_select)
        self.assertEqual(decision.letters, ["A"])

    def test_auto_practice_clicks_visible_answer(self):
        decision = QuizAutomationAgent("auto_practice").decide(["A", "C"], option_count=4)

        self.assertTrue(decision.should_select)
        self.assertTrue(decision.should_close)
        self.assertEqual(decision.letters, ["A", "C"])

    def test_no_letters_never_clicks(self):
        decision = QuizAutomationAgent("auto_practice").decide([], option_count=4)

        self.assertFalse(decision.should_select)


if __name__ == "__main__":
    unittest.main()

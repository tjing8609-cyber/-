import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from quiz_agent import QuizAutomationAgent  # noqa: E402
from quiz_popup_agent import QuizPopupToolbox, run_quiz_popup_agent  # noqa: E402


class FakePopupTools:
    def __init__(self, visible_letters=None, api_letters=None, multi=False, has_options=True):
        self.visible_letters = visible_letters or []
        self.api_letters = api_letters or []
        self.multi = multi
        self.options = ["A", "B", "C"] if has_options else []
        self.selected = []
        self.single_clicked = []
        self.submitted = False
        self.closed = False
        self.scrolls = []
        self.waits = []

    def toolbox(self):
        return QuizPopupToolbox(
            check_for_quiz=lambda: True,
            scroll_dialog=self.scroll_dialog,
            extract_visible_answers=lambda: self.visible_letters,
            get_options=lambda: self.options,
            is_multi_choice=lambda: self.multi,
            select_options=self.select_options,
            click_single_option=self.click_single_option,
            submit=self.submit,
            close=self.close,
            answer_with_api=lambda _options: self.api_letters,
            wait=lambda seconds: self.waits.append(seconds),
        )

    def scroll_dialog(self, position):
        self.scrolls.append(position)
        return True

    def select_options(self, letters):
        self.selected.extend(letters)
        return True

    def click_single_option(self, letter, options):
        self.single_clicked.append((letter, options))
        return True

    def submit(self):
        self.submitted = True
        return True

    def close(self):
        self.closed = True
        return True


class QuizPopupAgentTests(unittest.TestCase):
    def test_auto_practice_uses_deepseek_answer_and_submits(self):
        tools = FakePopupTools(api_letters=["B"])

        self.assertTrue(run_quiz_popup_agent(QuizAutomationAgent("auto_practice"), tools.toolbox()))
        self.assertEqual(tools.single_clicked[0][0], "B")
        self.assertTrue(tools.submitted)
        self.assertTrue(tools.closed)

    def test_semi_auto_selects_without_submit_or_close(self):
        tools = FakePopupTools(api_letters=["A"], multi=True)

        self.assertTrue(run_quiz_popup_agent(QuizAutomationAgent("semi_auto"), tools.toolbox()))
        self.assertEqual(tools.selected, ["A"])
        self.assertFalse(tools.submitted)
        self.assertFalse(tools.closed)

    def test_returns_false_when_no_options(self):
        tools = FakePopupTools(api_letters=["A"], has_options=False)

        self.assertFalse(run_quiz_popup_agent(QuizAutomationAgent("auto_practice"), tools.toolbox()))


if __name__ == "__main__":
    unittest.main()

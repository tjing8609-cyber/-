import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from quiz_popup_actions import click_quiz_popup_submit  # noqa: E402


class FakeElement:
    def __init__(self, text="", displayed=True, children=None):
        self.text = text
        self.displayed = displayed
        self.children = children or []
        self.clicked = False

    def is_displayed(self):
        return self.displayed

    def click(self):
        self.clicked = True

    def find_elements(self, by, value):
        return self.children


class FakeDriver:
    def __init__(self, dialogs):
        self.dialogs = dialogs

    def find_elements(self, by, value):
        return self.dialogs

    def execute_script(self, script, element):
        element.click()


class QuizPopupActionsTests(unittest.TestCase):
    def test_clicks_submit_inside_visible_dialog(self):
        submit = FakeElement("提交")
        dialog = FakeElement(children=[submit])
        driver = FakeDriver([dialog])

        self.assertTrue(click_quiz_popup_submit(driver))
        self.assertTrue(submit.clicked)

    def test_blocks_formal_exam_submit_text(self):
        submit = FakeElement("确认提交")
        dialog = FakeElement(children=[submit])
        driver = FakeDriver([dialog])

        self.assertFalse(click_quiz_popup_submit(driver))
        self.assertFalse(submit.clicked)

    def test_hidden_dialog_is_ignored(self):
        submit = FakeElement("提交")
        dialog = FakeElement(displayed=False, children=[submit])
        driver = FakeDriver([dialog])

        self.assertFalse(click_quiz_popup_submit(driver))
        self.assertFalse(submit.clicked)


if __name__ == "__main__":
    unittest.main()

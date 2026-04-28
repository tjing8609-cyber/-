import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from quiz_popup_actions import (  # noqa: E402
    click_quiz_popup_submit,
    is_multi_choice_dialog,
    select_options_by_letters,
    visible_quiz_options,
)


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
        self.scripts = []

    def find_elements(self, by, value):
        return self.dialogs

    def execute_script(self, script, element=None):
        self.scripts.append((script, element))
        if element is None:
            return
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

    def test_visible_quiz_options_filters_hidden(self):
        visible = FakeElement("A")
        hidden = FakeElement("B", displayed=False)
        driver = FakeDriver([visible, hidden])

        self.assertEqual(visible_quiz_options(driver, ["//option"]), [visible])

    def test_is_multi_choice_by_title_or_checkbox(self):
        title = FakeElement("多选题")
        self.assertTrue(is_multi_choice_dialog(FakeDriver([title])))

    def test_select_options_by_letters_clicks_expected_options(self):
        option_a = FakeElement("A")
        option_b = FakeElement("B")
        driver = FakeDriver([])

        self.assertTrue(select_options_by_letters(driver, [option_a, option_b], ["B"]))
        self.assertFalse(option_a.clicked)
        self.assertTrue(option_b.clicked)


if __name__ == "__main__":
    unittest.main()

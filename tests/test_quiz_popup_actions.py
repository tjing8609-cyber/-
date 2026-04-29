import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from quiz_popup_actions import (  # noqa: E402
    click_first_non_quiz_dialog_close,
    click_quiz_popup_submit,
    is_multi_choice_dialog,
    probable_quiz_dialogs,
    select_options_by_letters,
    visible_blocking_dialogs,
    visible_quiz_dialogs,
    visible_quiz_options,
)


class FakeElement:
    def __init__(self, text="", displayed=True, children=None, attrs=None):
        self.text = text
        self.displayed = displayed
        self.children = children or []
        self.attrs = attrs or {}
        self.clicked = False

    def is_displayed(self):
        return self.displayed

    def click(self):
        self.clicked = True

    def find_elements(self, by, value):
        if "ques-list" in value or "question-info" in value:
            return [child for child in self.children if child.attrs.get("role") == "quiz-marker"]
        if "option" in value:
            return [child for child in self.children if child.attrs.get("role") == "option"]
        return self.children

    def get_attribute(self, name):
        return self.attrs.get(name, "")


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

    def test_visible_quiz_dialogs_detects_ai_practice_popup(self):
        page = FakeElement("页面背景")
        dialog = FakeElement("AI随堂练习\n1.【多选题】\nA 政治安全\nB 人民安全\n提交作答")
        driver = FakeDriver([page, dialog])

        self.assertEqual(visible_quiz_dialogs(driver), [dialog])

    def test_visible_quiz_dialogs_does_not_choose_submit_button_only(self):
        submit = FakeElement("提交作答")
        dialog = FakeElement("AI随堂练习\n1.【多选题】\nA 政治安全\nB 人民安全\n提交作答")
        driver = FakeDriver([submit, dialog])

        self.assertEqual(visible_quiz_dialogs(driver), [dialog])

    def test_probable_quiz_dialogs_do_not_fallback_to_generic_dialog(self):
        dialog = FakeElement("学前必读\n知道了")
        driver = FakeDriver([dialog])

        self.assertEqual(probable_quiz_dialogs(driver), [])
        self.assertEqual(visible_quiz_dialogs(driver), [dialog])

    def test_visible_blocking_dialogs_returns_visible_dialogs(self):
        visible = FakeElement("学前必读")
        hidden = FakeElement("隐藏", displayed=False)
        driver = FakeDriver([visible, hidden])

        self.assertEqual(visible_blocking_dialogs(driver), [visible])

    def test_click_first_non_quiz_dialog_close_skips_quiz_dialog(self):
        quiz_close = FakeElement("关闭")
        normal_close = FakeElement("知道了")
        quiz_dialog = FakeElement("AI随堂练习\n1.【单选题】\nA 是\nB 否\n提交作答", children=[quiz_close])
        normal_dialog = FakeElement("学前必读", children=[normal_close])
        driver = FakeDriver([quiz_dialog, normal_dialog])

        self.assertTrue(click_first_non_quiz_dialog_close(driver))
        self.assertFalse(quiz_close.clicked)
        self.assertTrue(normal_close.clicked)

    def test_probable_quiz_dialogs_detects_ai_exercise_container_class(self):
        dialog = FakeElement(
            "1.【多选题】\n下列关于政治安全表述正确的有（）。\nA 政治安全仅关乎党和国家安危\nB 政治安全是根本保障\n提交作答",
            attrs={"class": "el-dialog ai-class-exercise-dialog"},
        )
        driver = FakeDriver([dialog])

        self.assertEqual(probable_quiz_dialogs(driver), [dialog])


if __name__ == "__main__":
    unittest.main()

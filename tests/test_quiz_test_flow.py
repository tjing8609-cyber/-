import sys
import unittest
from pathlib import Path

from selenium.webdriver.common.by import By


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from quiz_test_flow import (  # noqa: E402
    find_start_button,
    first_quiz_status,
    is_answer_card_ready_for_submit,
    is_last_question,
    is_quiz_completed,
    submit_quiz,
)


class FakeElement:
    def __init__(self, text="", classes="", css=None, displayed=True, enabled=True, attrs=None, children=None):
        self.text = text
        self.classes = classes
        self.css = css or {}
        self.displayed = displayed
        self.enabled = enabled
        self.attrs = attrs or {}
        self.children = children or {}
        self.clicked = False

    def click(self):
        self.clicked = True

    def find_elements(self, by, value):
        return self.children.get((by, value), [])

    def get_attribute(self, name):
        if name == "class":
            return self.classes
        return self.attrs.get(name)

    def value_of_css_property(self, name):
        return self.css.get(name, "")

    def is_displayed(self):
        return self.displayed

    def is_enabled(self):
        return self.enabled


class FakeDriver:
    def __init__(self, elements=None):
        self.elements = elements or {}
        self.scripts = []

    def find_elements(self, by, value):
        return self.elements.get((by, value), [])

    def execute_script(self, script, *args):
        self.scripts.append((script, args))


class QuizTestFlowTests(unittest.TestCase):
    def test_first_quiz_status(self):
        driver = FakeDriver({
            (By.XPATH, "//span[contains(text(), '已提交')]"): [FakeElement("已提交")]
        })

        self.assertEqual(first_quiz_status(driver), "已提交")

    def test_answer_card_ready_for_submit(self):
        items = [
            FakeElement("1", classes="greenbgcur"),
            FakeElement("2", classes="greenbgcur"),
            FakeElement("3", classes="greenbordercur"),
        ]
        driver = FakeDriver({
            (By.XPATH, "//li[contains(@class, 'questionlistall') or contains(@class, 'green')]"): items
        })

        self.assertTrue(is_answer_card_ready_for_submit(driver))

    def test_is_last_question_requires_disabled_next_and_answer_card(self):
        items = [
            FakeElement("1", classes="greenbgcur"),
            FakeElement("2", classes="greenbordercur"),
        ]
        driver = FakeDriver({
            (By.XPATH, "//span[contains(@class, 'Topicswitchingbtn-gray')]"): [FakeElement("下一题")],
            (By.XPATH, "//li[contains(@class, 'questionlistall') or contains(@class, 'green')]"): items,
        })

        self.assertTrue(is_last_question(driver))

    def test_find_start_button_prefers_start_doing_text(self):
        button = FakeElement("开始做题")
        container = FakeElement(children={
            (By.XPATH, ".//button[contains(text(), '开始做题')]"): [button]
        })

        self.assertIs(find_start_button(FakeDriver(), container), button)

    def test_quiz_completed_by_progress(self):
        quiz = FakeElement("章节测试", attrs={"id": "quiz-1"})

        self.assertTrue(is_quiz_completed(quiz, progress={"completed_quizzes": ["quiz-1"]}))

    def test_submit_quiz_clicks_submit_and_confirm(self):
        submit = FakeElement("提交")
        confirm = FakeElement("确认")
        driver = FakeDriver({
            (By.XPATH, "//button[contains(text(), '提交')]"): [submit],
            (By.XPATH, "//button[contains(@class, 'Submissionbtn') and contains(@class, 'el-button--primary')]"): [confirm],
        })

        self.assertTrue(submit_quiz(driver, wait_func=lambda _seconds: None))
        self.assertTrue(submit.clicked)
        self.assertTrue(confirm.clicked)


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path

from selenium.webdriver.common.by import By


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from quiz_navigation import (  # noqa: E402
    find_quiz_entrance,
    is_completed_quiz_text,
    quiz_entry_selectors,
    scroll_to_load_all_quizzes,
    switch_to_exam_tab,
)


class FakeElement:
    def __init__(self, text=""):
        self.text = text
        self.clicked = False

    def click(self):
        self.clicked = True


class FakeDriver:
    def __init__(self, elements=None):
        self.elements = elements or {}
        self.scripts = []

    def find_elements(self, by, value):
        return self.elements.get((by, value), [])

    def execute_script(self, script, *args):
        self.scripts.append((script, args))


class QuizNavigationTests(unittest.TestCase):
    def test_quiz_entry_selectors_include_quiz_type(self):
        selectors = quiz_entry_selectors("章节测试")

        self.assertTrue(any("章节测试" in selector for selector in selectors))

    def test_completed_quiz_text(self):
        self.assertTrue(is_completed_quiz_text("第一章测试 已提交"))
        self.assertFalse(is_completed_quiz_text("第一章测试 开始做题"))

    def test_switch_to_exam_tab_clicks_matching_tab(self):
        tab = FakeElement("作业考试")
        driver = FakeDriver({
            (By.XPATH, "//div[contains(text(), '作业考试')]"): [tab]
        })

        self.assertTrue(switch_to_exam_tab(driver, wait_func=lambda _seconds: None))
        self.assertTrue(tab.clicked)

    def test_scroll_to_load_all_quizzes_uses_container_when_found(self):
        container = FakeElement()
        driver = FakeDriver({
            (By.XPATH, "//div[contains(@class, 'homework-list')]"): [container]
        })

        scroll_to_load_all_quizzes(driver, wait_func=lambda _seconds: None)

        self.assertEqual(len(driver.scripts), 2)
        self.assertIs(driver.scripts[0][1][0], container)

    def test_find_quiz_entrance_returns_start_button(self):
        quiz = FakeElement("章节测试 开始做题")
        start = FakeElement("开始做题")
        driver = FakeDriver({
            (By.XPATH, "//div[contains(text(), '章节测试')]"): [quiz]
        })

        entrance = find_quiz_entrance(
            driver,
            "章节测试",
            find_start_button=lambda element: start if element is quiz else None,
            wait_func=lambda _seconds: None,
        )

        self.assertTrue(entrance.found)
        self.assertIs(entrance.container, quiz)
        self.assertIs(entrance.start_button, start)


if __name__ == "__main__":
    unittest.main()

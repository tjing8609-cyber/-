import sys
import unittest
from pathlib import Path

from selenium.webdriver.common.by import By


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

import quiz_page_actions  # noqa: E402
from quiz_page_actions import (  # noqa: E402
    click_next_button,
    find_clickable_option_element,
    find_next_button,
    is_next_button_disabled,
    select_answer_options,
)


class FakeElement:
    def __init__(self, text="", classes="", children=None):
        self.text = text
        self.classes = classes
        self.children = children or {}

    def find_element(self, by, value):
        elements = self.children.get((by, value), [])
        if elements:
            return elements[0]
        raise RuntimeError("not found")

    def get_attribute(self, name):
        if name == "class":
            return self.classes
        return ""


class FakeDriver:
    def __init__(self, elements=None):
        self.elements = elements or {}
        self.scripts = []

    def find_elements(self, by, value):
        return self.elements.get((by, value), [])

    def execute_script(self, script, *args):
        self.scripts.append((script, args))


class QuizPageActionsTests(unittest.TestCase):
    def test_find_clickable_option_element_prefers_radio_inner(self):
        inner = FakeElement()
        parent = FakeElement(children={
            (By.XPATH, ".//span[contains(@class, 'el-radio__inner')]"): [inner]
        })

        self.assertIs(find_clickable_option_element(parent), inner)

    def test_find_next_button_skips_disabled(self):
        disabled = FakeElement("下一题", classes="disabled")
        enabled = FakeElement("下一题", classes="next")
        driver = FakeDriver({
            (By.XPATH, "//span[contains(@class, 'Topicswitchingbtn') and contains(text(), '下一题')]"): [disabled, enabled]
        })

        self.assertIs(find_next_button(driver), enabled)

    def test_is_next_button_disabled(self):
        driver = FakeDriver({
            (By.XPATH, "//span[contains(@class, 'Topicswitchingbtn-gray')]"): [FakeElement("下一题")]
        })

        self.assertTrue(is_next_button_disabled(driver))

    def test_select_answer_options_clicks_each_answer(self):
        clicked = []
        original_action_click = quiz_page_actions.action_click
        quiz_page_actions.action_click = lambda _driver, element, min_pause=0.3, max_pause=0.8: clicked.append(element)
        try:
            option_a = FakeElement("A")
            option_b = FakeElement("B")
            question_data = {
                "type": "multiple",
                "options": {
                    "A": {"element": option_a},
                    "B": {"element": option_b},
                },
            }

            self.assertTrue(select_answer_options(FakeDriver(), ["A", "B"], question_data, wait_func=lambda _seconds: None))
            self.assertEqual(clicked, [option_a, option_b])
        finally:
            quiz_page_actions.action_click = original_action_click

    def test_click_next_button_uses_action_click(self):
        clicked = []
        original_action_click = quiz_page_actions.action_click
        quiz_page_actions.action_click = lambda _driver, element, min_pause=0.5, max_pause=1.0: clicked.append(element)
        try:
            next_button = FakeElement("下一题", classes="next")
            driver = FakeDriver({
                (By.XPATH, "//span[contains(@class, 'Topicswitchingbtn') and contains(text(), '下一题')]"): [next_button]
            })

            self.assertTrue(click_next_button(driver, wait_func=lambda _seconds: None))
            self.assertEqual(clicked, [next_button])
        finally:
            quiz_page_actions.action_click = original_action_click


if __name__ == "__main__":
    unittest.main()

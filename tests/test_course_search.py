import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from course_search import course_name_selectors, enter_study_page, find_and_click_course_by_name  # noqa: E402


class FakeElement:
    def __init__(self, text="", fail_click=False):
        self.text = text
        self.fail_click = fail_click
        self.clicked = False

    def click(self):
        if self.fail_click:
            raise RuntimeError("click failed")
        self.clicked = True

    def is_displayed(self):
        return True

    def find_elements(self, by, value):
        return []


class FakeSwitch:
    def __init__(self):
        self.switched = []

    def window(self, handle):
        self.switched.append(handle)


class FakeDriver:
    def __init__(self, elements=None):
        self.current_url = "https://example.test"
        self.elements = elements or {}
        self.scripts = []
        self.window_handles = ["a"]
        self.switch_to = FakeSwitch()

    def find_elements(self, by, value):
        return self.elements.get(value, [])

    def execute_script(self, script, *args):
        self.scripts.append((script, args))


class CourseSearchTests(unittest.TestCase):
    def test_course_name_selectors_include_name(self):
        selectors = course_name_selectors("国家安全教育")

        self.assertTrue(any("国家安全教育" in selector for selector in selectors))
        self.assertFalse(any("近现代史" in selector for selector in selectors))

    def test_course_name_selectors_can_include_history_fallbacks(self):
        selectors = course_name_selectors("中国近现代史纲要", include_history_fallback=True)

        self.assertTrue(any("近现代史纲要" in selector for selector in selectors))

    def test_find_and_click_course_by_name_clicks_matching_element(self):
        selector = "//*[contains(text(), '国家安全教育')]"
        element = FakeElement("国家安全教育")
        driver = FakeDriver(elements={selector: [element]})

        self.assertTrue(find_and_click_course_by_name(driver, "国家安全教育", selectors=[selector]))
        self.assertTrue(element.clicked)

    def test_find_and_click_course_by_name_returns_false_without_match(self):
        driver = FakeDriver()

        self.assertFalse(find_and_click_course_by_name(driver, "不存在", selectors=["//bad"]))

    def test_enter_study_page_uses_enter_button_when_present(self):
        button = FakeElement("继续学习")
        driver = FakeDriver(elements={"//*[contains(text(),'继续学习')]": [button]})

        self.assertTrue(enter_study_page(driver))
        self.assertTrue(button.clicked)


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from page_detection import (  # noqa: E402
    is_captcha_present,
    is_course_page_ready,
    is_quiz_dialog_present,
    is_video_present,
    try_click_enter_study,
)


class FakeElement:
    def __init__(self, displayed=True):
        self.displayed = displayed
        self.clicked = False

    def is_displayed(self):
        return self.displayed

    def click(self):
        self.clicked = True


class FakeDriver:
    def __init__(self, current_url="", page_source="", by_tag=None, by_xpath=None):
        self.current_url = current_url
        self.page_source = page_source
        self.by_tag = by_tag or {}
        self.by_xpath = by_xpath or {}
        self.scripts = []

    def find_elements(self, by, value):
        key = (by, value)
        if key in self.by_xpath:
            return self.by_xpath[key]
        if key in self.by_tag:
            return self.by_tag[key]
        if by == "xpath":
            return [element for text, element in self.by_xpath.items() if isinstance(text, str) and text in value]
        return []

    def execute_script(self, script, *args):
        self.scripts.append((script, args))


class PageDetectionTests(unittest.TestCase):
    def test_course_ready_by_url(self):
        driver = FakeDriver(current_url="https://example.com/study/index")

        self.assertTrue(is_course_page_ready(driver))

    def test_video_present(self):
        driver = FakeDriver(by_tag={("tag name", "video"): [FakeElement()]})

        self.assertTrue(is_video_present(driver))

    def test_course_ready_by_marker(self):
        driver = FakeDriver(page_source="这里有课程目录和章节")

        self.assertTrue(is_course_page_ready(driver))

    def test_quiz_dialog_present_filters_hidden(self):
        driver = FakeDriver(by_xpath={
            ("xpath", "//div[contains(@class,'el-dialog__wrapper') and not(contains(@style,'display: none'))]"): [
                FakeElement(displayed=False),
                FakeElement(displayed=True),
            ]
        })

        self.assertTrue(is_quiz_dialog_present(driver))

    def test_try_click_enter_study(self):
        button = FakeElement()
        driver = FakeDriver(by_xpath={
            ("xpath", "//*[contains(text(),'继续学习')]"): [button]
        })

        self.assertTrue(try_click_enter_study(driver))
        self.assertTrue(button.clicked)

    def test_captcha_present_by_source(self):
        driver = FakeDriver(page_source="请完成滑块验证")

        self.assertTrue(is_captcha_present(driver))


if __name__ == "__main__":
    unittest.main()

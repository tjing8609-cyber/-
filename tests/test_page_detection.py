import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from page_detection import (  # noqa: E402
    close_question_popup,
    detect_course_layout,
    is_captcha_present,
    is_course_list_page,
    is_course_page_ready,
    is_quiz_dialog_present,
    is_video_present,
    try_click_enter_study,
    wait_for_captcha_completion,
)


class FakeElement:
    def __init__(self, displayed=True, location=None):
        self.displayed = displayed
        self.clicked = False
        self.location = location or {"x": 0, "y": 0}

    def is_displayed(self):
        return self.displayed

    def click(self):
        self.clicked = True


class FakeDriver:
    def __init__(self, current_url="", page_source="", by_tag=None, by_xpath=None, window_width=1000):
        self.current_url = current_url
        self.page_source = page_source
        self.by_tag = by_tag or {}
        self.by_xpath = by_xpath or {}
        self.scripts = []
        self.window_width = window_width

    def find_elements(self, by, value):
        key = (by, value)
        if key in self.by_xpath:
            return self.by_xpath[key]
        if key in self.by_tag:
            return self.by_tag[key]
        if by == "xpath":
            return [element for text, element in self.by_xpath.items() if isinstance(text, str) and text in value]
        return []

    def find_element(self, by, value):
        elements = self.find_elements(by, value)
        if not elements:
            raise RuntimeError("not found")
        return elements[0]

    def execute_script(self, script, *args):
        self.scripts.append((script, args))
        if "innerWidth" in script:
            return self.window_width


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

    def test_course_list_page_by_marker(self):
        driver = FakeDriver(page_source="第二章 课程 视频")

        self.assertTrue(is_course_list_page(driver))

    def test_close_question_popup_clicks_close_button(self):
        close_button = FakeElement()
        driver = FakeDriver(by_xpath={
            ("xpath", "//div[contains(@class, 'el-dialog__close')]"): [close_button]
        })

        self.assertTrue(close_question_popup(driver))
        self.assertTrue(close_button.clicked)

    def test_detect_course_layout_sidebar_when_panel_on_right(self):
        sidebar = FakeElement(location={"x": 800, "y": 0})
        driver = FakeDriver(by_xpath={
            ("xpath", "//div[contains(@class, 'catalog') or contains(@class, '目录')]"): [sidebar]
        }, window_width=1000)

        self.assertEqual(detect_course_layout(driver), "sidebar")

    def test_wait_for_captcha_completion_returns_after_login_success(self):
        sleep_calls = []

        self.assertTrue(wait_for_captcha_completion(
            check_captcha=lambda: True,
            check_login_success=lambda: True,
            sleep_func=lambda seconds: sleep_calls.append(seconds),
        ))
        self.assertEqual(sleep_calls, [2])


if __name__ == "__main__":
    unittest.main()

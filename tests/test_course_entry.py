import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from course_entry import click_entry_dialogs, has_course_url, normalize_course_url, open_course_url  # noqa: E402


class FakeElement:
    def __init__(self, displayed=True, fail_click=False):
        self.displayed = displayed
        self.fail_click = fail_click
        self.clicked = False

    def is_displayed(self):
        return self.displayed

    def click(self):
        if self.fail_click:
            raise RuntimeError("click failed")
        self.clicked = True


class FakeDriver:
    def __init__(self, elements=None, fail_get=False):
        self.elements = elements or {}
        self.fail_get = fail_get
        self.urls = []
        self.scripts = []

    def get(self, url):
        if self.fail_get:
            raise RuntimeError("navigation failed")
        self.urls.append(url)

    def find_elements(self, by, value):
        return self.elements.get(value, [])

    def execute_script(self, script, *args):
        self.scripts.append((script, args))
        if args:
            args[0].clicked = True


class CourseEntryTests(unittest.TestCase):
    def test_course_url_helpers(self):
        self.assertEqual(normalize_course_url("  https://example.test  "), "https://example.test")
        self.assertTrue(has_course_url("https://example.test"))
        self.assertFalse(has_course_url("  "))

    def test_click_entry_dialogs_clicks_visible_button(self):
        button = FakeElement()
        driver = FakeDriver(elements={
            "//button[contains(@class,'agree-btn')]": [button]
        })

        self.assertEqual(click_entry_dialogs(driver), 1)
        self.assertTrue(button.clicked)

    def test_click_entry_dialogs_falls_back_to_script_click(self):
        button = FakeElement(fail_click=True)
        driver = FakeDriver(elements={
            "//button[contains(@class,'agree-btn')]": [button]
        })

        self.assertEqual(click_entry_dialogs(driver), 1)
        self.assertTrue(button.clicked)
        self.assertTrue(driver.scripts)

    def test_open_course_url_waits_for_ready(self):
        driver = FakeDriver()
        calls = []

        ok = open_course_url(
            driver,
            "https://course.test",
            wait_ready_func=lambda: calls.append("ready") or True,
            wait_func=lambda seconds: calls.append(seconds),
        )

        self.assertTrue(ok)
        self.assertEqual(driver.urls, ["https://course.test"])
        self.assertIn("ready", calls)

    def test_open_course_url_falls_back_to_wait_ready_after_navigation_error(self):
        driver = FakeDriver(fail_get=True)

        self.assertTrue(open_course_url(driver, "https://course.test", wait_ready_func=lambda: True))


if __name__ == "__main__":
    unittest.main()

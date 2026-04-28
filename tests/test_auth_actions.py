import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from auth_actions import find_login_button, login_method_script  # noqa: E402


class FakeElement:
    def __init__(self, text=""):
        self.text = text
        self.clicked = False

    def click(self):
        self.clicked = True

    def is_displayed(self):
        return True

    def is_enabled(self):
        return True


class FakeDriver:
    def __init__(self, elements=None, script_result=True):
        self.elements = elements or []
        self.script_result = script_result
        self.scripts = []

    def find_elements(self, by, value):
        return self.elements

    def find_element(self, by, value):
        if not self.elements:
            raise RuntimeError("not found")
        return self.elements[0]

    def execute_script(self, script, *args):
        self.scripts.append((script, args))
        if "click" in script and args:
            args[0].click()
        return self.script_result


class AuthActionsTests(unittest.TestCase):
    def test_find_login_button_uses_text(self):
        button = FakeElement("登录")

        self.assertIs(find_login_button(FakeDriver([button])), button)

    def test_login_method_script_clicks_submit(self):
        button = FakeElement("登录")
        driver = FakeDriver([button])

        self.assertTrue(login_method_script(driver, "user", "pass"))
        self.assertTrue(button.clicked)

    def test_login_method_script_returns_false_when_inputs_missing(self):
        driver = FakeDriver(script_result=False)

        self.assertFalse(login_method_script(driver, "user", "pass"))


if __name__ == "__main__":
    unittest.main()

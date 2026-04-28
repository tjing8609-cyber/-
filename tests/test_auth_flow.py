import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from auth_flow import (  # noqa: E402
    is_login_required,
    is_login_required_state,
    is_login_success,
    is_login_success_state,
    mask_username,
)


class FakeDriver:
    def __init__(self, current_url="", page_source=""):
        self.current_url = current_url
        self.page_source = page_source


class AuthFlowTests(unittest.TestCase):
    def test_mask_username_matches_legacy_shape(self):
        self.assertEqual(mask_username("13800138000"), "138****00")
        self.assertEqual(mask_username("abc"), "abc******")
        self.assertEqual(mask_username(""), "")

    def test_login_required_by_url_or_source(self):
        self.assertTrue(is_login_required_state("https://example.com/login", ""))
        self.assertTrue(is_login_required_state("", "请输入手机号"))
        self.assertFalse(is_login_required_state("https://example.com/home", "我的课程"))

    def test_login_success_by_url_or_source(self):
        self.assertTrue(is_login_success_state("https://onlineweb.zhihuishu.com/onlinestuh5", ""))
        self.assertTrue(is_login_success_state("", "我的课程"))
        self.assertFalse(is_login_success_state("https://example.com/login", "登录"))

    def test_driver_helpers_read_page_state(self):
        driver = FakeDriver("https://example.com/login", "登录")
        self.assertTrue(is_login_required(driver))

        driver = FakeDriver("https://onlineweb.zhihuishu.com/onlinestuh5", "")
        self.assertTrue(is_login_success(driver))


if __name__ == "__main__":
    unittest.main()

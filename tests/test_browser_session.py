import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from browser_session import hide_webdriver_flag, resolve_local_driver_paths  # noqa: E402


class FakeDriver:
    def __init__(self, should_raise=False):
        self.should_raise = should_raise
        self.scripts = []

    def execute_script(self, script):
        if self.should_raise:
            raise RuntimeError("boom")
        self.scripts.append(script)


class BrowserSessionTests(unittest.TestCase):
    def test_resolve_local_driver_paths_deduplicates_existing_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code_dir = root / "code"
            code_dir.mkdir()
            local_driver = code_dir / "chromedriver.exe"
            local_driver.write_text("", encoding="utf-8")

            paths = resolve_local_driver_paths(root, cwd=code_dir)

            self.assertEqual(paths, [str(local_driver)])

    def test_hide_webdriver_flag_runs_script(self):
        driver = FakeDriver()

        self.assertTrue(hide_webdriver_flag(driver))
        self.assertIn("navigator", driver.scripts[0])

    def test_hide_webdriver_flag_returns_false_on_failure(self):
        self.assertFalse(hide_webdriver_flag(FakeDriver(should_raise=True)))


if __name__ == "__main__":
    unittest.main()

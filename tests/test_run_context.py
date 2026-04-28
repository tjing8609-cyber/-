import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from config_loader import ConfigLoadError, load_json_config  # noqa: E402
from run_context import create_run_context, normalize_course_type  # noqa: E402


class RunContextTests(unittest.TestCase):
    def test_resolves_default_launch_account_from_code_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code_dir = root / "code"
            launch_dir = root / "启动"
            code_dir.mkdir()
            launch_dir.mkdir()
            account_file = launch_dir / "account.json"
            account_file.write_text(
                json.dumps({"mode": "video", "course_type": "2", "course_name": "国家安全教育"}, ensure_ascii=False),
                encoding="utf-8",
            )

            context = create_run_context("account.json", code_dir=code_dir)

            self.assertEqual(context.account_path, account_file.resolve())
            self.assertEqual(context.mode, "video")
            self.assertEqual(context.course_type, 2)
            self.assertEqual(context.course_name, "国家安全教育")

    def test_load_json_config_supports_gbk(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "account.json"
            config_file.write_text(
                json.dumps({"course_name": "国家安全教育"}, ensure_ascii=False),
                encoding="gbk",
            )

            self.assertEqual(load_json_config(config_file)["course_name"], "国家安全教育")

    def test_rejects_non_object_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "account.json"
            config_file.write_text("[]", encoding="utf-8")

            with self.assertRaises(ConfigLoadError):
                load_json_config(config_file)

    def test_invalid_course_type_is_preserved_for_validation(self):
        self.assertEqual(normalize_course_type("2"), 2)
        self.assertEqual(normalize_course_type("bad"), "bad")


if __name__ == "__main__":
    unittest.main()

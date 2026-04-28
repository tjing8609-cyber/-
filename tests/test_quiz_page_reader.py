import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from quiz_page_reader import clean_question_text, detect_question_type_from_text, parse_option_text  # noqa: E402


class QuizPageReaderTests(unittest.TestCase):
    def test_clean_question_text_removes_number_type_and_score(self):
        self.assertEqual(
            clean_question_text("1. 【单选题】 (1分) 总体国家安全观的宗旨是什么？"),
            "总体国家安全观的宗旨是什么？",
        )

    def test_parse_option_text_detects_label(self):
        self.assertEqual(parse_option_text("A. 人民安全", "B"), ("A", "人民安全"))
        self.assertEqual(parse_option_text("B、政治安全", "A"), ("B", "政治安全"))

    def test_parse_option_text_uses_fallback(self):
        self.assertEqual(parse_option_text("人民安全", "C"), ("C", "人民安全"))

    def test_detect_question_type_from_text(self):
        self.assertEqual(detect_question_type_from_text("【多选题】"), "multiple")
        self.assertEqual(detect_question_type_from_text("【判断题】"), "judge")
        self.assertEqual(detect_question_type_from_text("", has_checkbox=True), "multiple")


if __name__ == "__main__":
    unittest.main()

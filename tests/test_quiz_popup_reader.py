import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from quiz_popup_reader import extract_question_from_dialog_text, strip_option_prefix  # noqa: E402


class QuizPopupReaderTests(unittest.TestCase):
    def test_strip_option_prefix(self):
        self.assertEqual(strip_option_prefix("A. 国家安全", "A"), "国家安全")
        self.assertEqual(strip_option_prefix("B、政治安全", "B"), "政治安全")
        self.assertEqual(strip_option_prefix("政治安全", "C"), "政治安全")

    def test_extract_question_ignores_options_and_buttons(self):
        text = "\n".join([
            "单选题",
            "总体国家安全观的宗旨是什么？",
            "A. 人民安全",
            "B. 政治安全",
            "提交",
        ])

        question = extract_question_from_dialog_text(text, option_texts=["人民安全", "政治安全"])

        self.assertEqual(question, "总体国家安全观的宗旨是什么？")


if __name__ == "__main__":
    unittest.main()

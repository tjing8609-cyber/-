import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from quiz_popup_reader import (  # noqa: E402
    build_popup_question_data,
    detect_question_type_from_text,
    extract_question_from_dialog_text,
    extract_question_from_page_dom,
    strip_option_prefix,
)


class FakeElement:
    def __init__(self, text="", displayed=True, children=None, role=""):
        self.text = text
        self.displayed = displayed
        self.children = children or []
        self.role = role

    def is_displayed(self):
        return self.displayed

    def find_elements(self, by, value):
        if "question-info" in value:
            return [child for child in self.children if child.role == "question"]
        return self.children


class FakeDriver:
    def __init__(self, dialogs, script_candidates=None):
        self.dialogs = dialogs
        self.script_candidates = script_candidates

    def find_elements(self, by, value):
        return self.dialogs

    def execute_script(self, script, element=None):
        if self.script_candidates is not None:
            return self.script_candidates
        return ""


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

    def test_extract_question_skips_ai_exercise_title_and_type(self):
        text = "\n".join([
            "AI随堂练习",
            "以下所有内容均由AI生成请注意甄别",
            "1.【多选题】",
            "下列关于政治安全表述正确的有（）。",
            "A 政治安全仅关乎党和国家安危",
            "B 政治安全是维护人民安全和国家利益的根本保障",
            "提交作答",
        ])

        question = extract_question_from_dialog_text(text)

        self.assertEqual(question, "下列关于政治安全表述正确的有（）。")

    def test_extract_question_from_compact_dialog_text(self):
        text = (
            "AI随堂练习以下所有内容均由AI生成请注意甄别"
            "1.[判断题]政治安全影响着军事安全、经济安全、社会安全、文化安全等各个领域的安全，"
            "国家安全的其他要素最终也要反映到维护政治安全上来。（）"
            "A 正确B 错误提交作答"
        )

        question = extract_question_from_dialog_text(text)

        self.assertEqual(
            question,
            "政治安全影响着军事安全、经济安全、社会安全、文化安全等各个领域的安全，国家安全的其他要素最终也要反映到维护政治安全上来。（）",
        )

    def test_extract_question_from_page_dom_script_candidates(self):
        driver = FakeDriver(
            [],
            script_candidates=[
                {
                    "questionText": "政治安全影响着军事安全、经济安全、社会安全、文化安全等各个领域的安全，国家安全的其他要素最终也要反映到维护政治安全上来。（）",
                    "rootText": "",
                    "rootHtml": "",
                }
            ],
        )

        question = extract_question_from_page_dom(driver)

        self.assertTrue(question.startswith("政治安全影响着军事安全"))

    def test_detect_question_type_from_text(self):
        self.assertEqual(detect_question_type_from_text("1.[判断题] 这是题干"), "judgement")
        self.assertEqual(detect_question_type_from_text("1.【多选题】 这是题干"), "multiple")
        self.assertEqual(detect_question_type_from_text("1.【单选题】 这是题干"), "single")

    def test_build_popup_question_data_reads_question_info_dom(self):
        question = FakeElement("下列关于政治安全表述正确的有（）。", role="question")
        dialog = FakeElement(
            "AI随堂练习\n1.【多选题】\nA 政治安全仅关乎党和国家安危\nB 政治安全是根本保障\n提交作答",
            children=[question],
        )
        option_a = FakeElement("A 政治安全仅关乎党和国家安危")
        option_b = FakeElement("B 政治安全是根本保障")

        data = build_popup_question_data(FakeDriver([dialog]), [option_a, option_b], question_type="multiple")

        self.assertEqual(data["question"], "下列关于政治安全表述正确的有（）。")
        self.assertEqual(data["type"], "multiple")
        self.assertEqual(data["options"]["A"]["text"], "政治安全仅关乎党和国家安危")

    def test_build_popup_question_data_sends_judgement_type_and_options(self):
        dialog = FakeElement(
            "AI随堂练习\n1.[判断题]\n政治安全影响着军事安全。（）\nA 正确\nB 错误\n提交作答"
        )
        option_a = FakeElement("A 正确")
        option_b = FakeElement("B 错误")

        data = build_popup_question_data(FakeDriver([dialog]), [option_a, option_b], question_type="single")

        self.assertEqual(data["type"], "judgement")
        self.assertEqual(data["options"]["A"]["text"], "正确")
        self.assertEqual(data["options"]["B"]["text"], "错误")


if __name__ == "__main__":
    unittest.main()

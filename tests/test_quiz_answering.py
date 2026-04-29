import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from quiz_answering import (  # noqa: E402
    QuizAnsweringService,
    allowed_option_labels,
    build_answer_messages,
    format_options_for_prompt,
    normalize_question_data,
    parse_answer_letters,
    question_type_label,
)


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, content='{"answer":"A"}'):
        self.content = content
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse(self.content)


class FakeClient:
    def __init__(self, content='{"answer":"A"}'):
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(content)


class QuizAnsweringTests(unittest.TestCase):
    def test_normalize_legacy_question_data(self):
        question = normalize_question_data({
            "question": "Which one?",
            "type": "single",
            "options": {
                "A": {"text": "Alpha", "element": object()},
                "B": {"text": "Beta", "element": object()},
            },
        })

        self.assertEqual(question.question, "Which one?")
        self.assertEqual(question.question_type, "single")
        self.assertEqual(question.options, {"A": "Alpha", "B": "Beta"})

    def test_allowed_option_labels_ignores_non_letters(self):
        labels = allowed_option_labels({
            "question": "q",
            "options": {"A": {"text": "a"}, "1": {"text": "bad"}, "C": {"text": "c"}},
        })

        self.assertEqual(labels, ["A", "C"])

    def test_parse_single_answer_from_sentence(self):
        result = parse_answer_letters("答案是 C。", ["A", "B", "C", "D"], "single")

        self.assertTrue(result.valid)
        self.assertEqual(result.value, "C")

    def test_parse_multiple_answer(self):
        result = parse_answer_letters("正确答案：A、C", ["A", "B", "C", "D"], "multiple")

        self.assertTrue(result.valid)
        self.assertEqual(result.value, ["A", "C"])

    def test_parse_json_answer_letters(self):
        result = parse_answer_letters('{"letters":["A","C"]}', ["A", "B", "C", "D"], "multiple")

        self.assertTrue(result.valid)
        self.assertEqual(result.value, ["A", "C"])

    def test_reject_multiple_answer_for_single_question(self):
        result = parse_answer_letters("AB", ["A", "B", "C"], "single")

        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "single question got multiple answers")

    def test_reject_disallowed_answer(self):
        result = parse_answer_letters("答案是 E", ["A", "B", "C", "D"], "single")

        self.assertFalse(result.valid)

    def test_build_answer_messages_contains_options(self):
        messages = build_answer_messages({
            "question": "Q?",
            "type": "multiple",
            "options": {"A": {"text": "One"}, "B": {"text": "Two"}},
        })

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("题目类型: 多选题", messages[1]["content"])
        self.assertIn("题干: Q?", messages[1]["content"])
        self.assertIn("A. One", messages[1]["content"])
        self.assertIn("B. Two", messages[1]["content"])

    def test_question_type_label_and_option_prompt_format(self):
        self.assertEqual(question_type_label("judgement"), "判断题")
        self.assertEqual(format_options_for_prompt({"A": "正确", "B": "错误"}), "A. 正确\nB. 错误")

    def test_answer_service_requests_json_output(self):
        client = FakeClient('{"answer":"B"}')
        service = QuizAnsweringService(client, "deepseek-chat")

        result = service.answer({
            "question": "判断题？",
            "type": "judgement",
            "options": {"A": {"text": "正确"}, "B": {"text": "错误"}},
        })

        call = client.chat.completions.calls[0]
        self.assertEqual(call["response_format"], {"type": "json_object"})
        self.assertIn("题目类型: 判断题", call["messages"][1]["content"])
        self.assertTrue(result.valid)
        self.assertEqual(result.value, "B")


if __name__ == "__main__":
    unittest.main()

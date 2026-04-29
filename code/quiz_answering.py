#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Core quiz answering helpers shared by quiz modes."""

import json
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential


ANSWER_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
QUESTION_TYPE_LABELS = {
    "single": "单选题",
    "multiple": "多选题",
    "judgement": "判断题",
    "judge": "判断题",
    "true_false": "判断题",
    "单选题": "单选题",
    "多选题": "多选题",
    "判断题": "判断题",
}


@dataclass
class QuestionData:
    question: str
    options: Dict[str, str]
    question_type: str = "single"


@dataclass
class AnswerResult:
    letters: List[str]
    raw_text: str = ""
    valid: bool = False
    reason: str = ""

    @property
    def value(self):
        if not self.valid:
            return None
        if len(self.letters) == 1:
            return self.letters[0]
        return self.letters


def normalize_question_data(question_data) -> QuestionData:
    """Convert legacy dict question payloads into a small stable model."""
    if isinstance(question_data, QuestionData):
        return question_data

    raw_options = question_data.get("options") or {}
    normalized_options = {}
    for label, value in raw_options.items():
        option_label = str(label).strip().upper()
        if not option_label:
            continue
        if isinstance(value, dict):
            text = str(value.get("text", "")).strip()
        else:
            text = str(value).strip()
        if text:
            normalized_options[option_label] = text

    return QuestionData(
        question=str(question_data.get("question", "")).strip(),
        options=normalized_options,
        question_type=str(question_data.get("type", "single")).strip() or "single",
    )


def question_type_label(question_type: str) -> str:
    normalized = str(question_type or "single").strip()
    return QUESTION_TYPE_LABELS.get(normalized, normalized or "单选题")


def format_options_for_prompt(options: Dict[str, str]) -> str:
    return "\n".join(f"{label}. {text}" for label, text in options.items())


def allowed_option_labels(question_data) -> List[str]:
    question = normalize_question_data(question_data)
    return [label for label in question.options.keys() if label in ANSWER_ALPHABET]


def build_answer_messages(question_data) -> List[dict]:
    question = normalize_question_data(question_data)
    options_text = format_options_for_prompt(question.options)
    type_label = question_type_label(question.question_type)
    user_prompt = (
        "请回答下面的题目。\n\n"
        f"题目类型: {type_label}\n"
        f"题干: {question.question}\n\n"
        f"选项:\n{options_text}\n\n"
        "要求: 只返回合法 json 对象，不要解释。"
        'JSON格式示例: {"answer":"A"} 或 {"answer":["A","C"]}。'
        "单选题或判断题返回一个字母，例如 A。"
        "多选题返回多个字母，例如 AC。"
    )
    return [
        {
            "role": "system",
            "content": (
                "你是选择题答题助手。你必须根据题目类型、题干和选项作答，"
                "并且只返回合法 json 对象，不要返回解释。"
                '输出格式固定为 {"answer":"A"} 或 {"answer":["A","C"]}。'
            ),
        },
        {"role": "user", "content": user_prompt},
    ]


def _extract_json_answer(text: str) -> Optional[str]:
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            value = (
                data.get("answer")
                or data.get("answers")
                or data.get("letter")
                or data.get("letters")
                or data.get("option")
                or data.get("options")
            )
            if isinstance(value, list):
                return "".join(str(item) for item in value)
            if value is not None:
                return str(value)
    except Exception:
        return None
    return None


def _candidate_answer_chunks(text: str) -> Iterable[str]:
    stripped = text.strip()
    json_answer = _extract_json_answer(stripped)
    if json_answer:
        yield json_answer

    upper = stripped.upper()
    patterns = [
        r"(?:答案|选项|ANSWER|ANS)\s*(?:是|为|:|：)?\s*([A-Z](?:[\s,，、/]+[A-Z])*)",
        r"^\s*([A-Z](?:[\s,，、/]*[A-Z])*)\s*$",
    ]
    for pattern in patterns:
        match = re.search(pattern, upper)
        if match:
            yield match.group(1)

    # Last resort: standalone letters only. This avoids collecting letters from
    # arbitrary English words such as "because".
    standalone = re.findall(r"(?<![A-Z])([A-Z])(?![A-Z])", upper)
    if standalone:
        yield "".join(standalone)


def parse_answer_letters(answer_text: str, allowed_labels: Iterable[str], question_type: str = "single") -> AnswerResult:
    allowed = [label.upper() for label in allowed_labels if label]
    allowed_set = set(allowed)
    if not answer_text or not allowed_set:
        return AnswerResult([], raw_text=answer_text or "", valid=False, reason="empty answer or options")

    for chunk in _candidate_answer_chunks(answer_text):
        letters = []
        for char in str(chunk).upper():
            if char in allowed_set and char not in letters:
                letters.append(char)
        if not letters:
            continue
        if question_type != "multiple" and len(letters) != 1:
            return AnswerResult(letters, raw_text=answer_text, valid=False, reason="single question got multiple answers")
        return AnswerResult(letters, raw_text=answer_text, valid=True)

    return AnswerResult([], raw_text=answer_text, valid=False, reason="no allowed option letters found")


def classify_api_error(error) -> str:
    error_text = str(error)
    mapping = [
        ("400", "400 request format error"),
        ("401", "401 authentication failed"),
        ("402", "402 insufficient balance"),
        ("422", "422 invalid request parameters"),
        ("429", "429 rate limit exceeded"),
        ("500", "500 server error"),
        ("503", "503 server busy"),
    ]
    for marker, label in mapping:
        if marker in error_text:
            return label
    return "unknown api error"


class QuizAnsweringService:
    def __init__(self, client, model: str, logger=None, temperature: float = 0.3, max_tokens: int = 64):
        self.client = client
        self.model = model
        self.logger = logger
        self.temperature = temperature
        self.max_tokens = max_tokens

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def answer(self, question_data) -> AnswerResult:
        if self.client is None:
            return AnswerResult([], valid=False, reason="api client is not configured")

        question = normalize_question_data(question_data)
        messages = build_answer_messages(question)
        if self.logger:
            options_preview = "; ".join(
                f"{label}. {text[:60]}" for label, text in question.options.items()
            )
            self.logger.info(
                f"🤖 调用DeepSeek获取答案: 类型={question_type_label(question.question_type)}; "
                f"题干={question.question[:120]}; 选项={options_preview}"
            )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=False,
        )
        answer_text = response.choices[0].message.content.strip()
        result = parse_answer_letters(answer_text, question.options.keys(), question.question_type)
        if self.logger:
            if result.valid:
                self.logger.info(f"✅ API返回答案: {result.value}")
            else:
                self.logger.warning(f"⚠️ API答案无效: {result.reason}; raw={answer_text!r}")
        return result

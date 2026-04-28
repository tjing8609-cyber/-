import re


QUESTION_NUMBER_RE = re.compile(r"^\d+[.、]\s*")
QUESTION_TYPE_RE = re.compile(r"【[^】]+】\s*")
SCORE_RE = re.compile(r"\(\d+分\)\s*")
OPTION_RE = re.compile(r"^\s*([A-F])(?:[.、）]|\s+)(.*)$")


def clean_question_text(text):
    value = str(text or "").strip()
    value = QUESTION_NUMBER_RE.sub("", value)
    value = QUESTION_TYPE_RE.sub("", value)
    value = SCORE_RE.sub("", value)
    return value.strip()


def parse_option_text(text, fallback_label):
    value = str(text or "").strip()
    if not value:
        return None, ""

    match = OPTION_RE.match(value)
    if match:
        label = match.group(1)
        option_text = match.group(2).strip()
        return label, option_text or value
    return fallback_label, value


def detect_question_type_from_text(text, has_checkbox=False, has_radio=False, default="single"):
    value = str(text or "")
    if "【多选题】" in value or "（多选）" in value:
        return "multiple"
    if "【判断题】" in value or "（判断）" in value:
        return "judge"
    if "【单选题】" in value or "（单选）" in value:
        return "single"
    if has_checkbox:
        return "multiple"
    if has_radio:
        return "single"
    return default


__all__ = [
    "clean_question_text",
    "detect_question_type_from_text",
    "parse_option_text",
]

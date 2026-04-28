import re
from dataclasses import dataclass

from quiz_popup_actions import visible_quiz_dialogs


OPTION_PREFIX_RE = re.compile(r"^\s*([A-Z])\s*[\.\u3001\uff09\)]?\s*(.*)$")
SKIP_QUESTION_LINES = {
    "单选题",
    "多选题",
    "判断题",
    "提交",
    "确定",
    "确认",
    "完成",
    "继续",
    "关闭",
}


@dataclass(frozen=True)
class PopupQuestionData:
    question: str
    options: dict
    question_type: str

    def as_legacy_dict(self):
        return {
            "question": self.question,
            "options": self.options,
            "type": self.question_type,
        }


def strip_option_prefix(text, fallback_label):
    raw_text = str(text or "").strip()
    match = OPTION_PREFIX_RE.match(raw_text)
    if match and match.group(1) == fallback_label:
        return match.group(2).strip() or raw_text
    return raw_text


def option_text_from_element(element, label):
    try:
        return strip_option_prefix(element.text, label)
    except Exception:
        return ""


def extract_question_from_dialog_text(dialog_text, option_texts=None):
    option_texts = {str(text).strip() for text in (option_texts or []) if str(text).strip()}
    for raw_line in str(dialog_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in option_texts or line in SKIP_QUESTION_LINES:
            continue
        if OPTION_PREFIX_RE.match(line):
            continue
        if len(line) >= 4:
            return line
    return ""


def read_visible_dialog_text(driver, dialog_xpath=None):
    dialogs = visible_quiz_dialogs(driver, dialog_xpath)
    for dialog in dialogs:
        try:
            text = (dialog.text or "").strip()
            if text:
                return text
        except Exception:
            continue
    return ""


def build_popup_question_data(driver, option_elements, question_type="single", dialog_xpath=None, logger=None):
    options = {}
    option_texts = []
    for index, element in enumerate(option_elements or []):
        label = chr(ord("A") + index)
        text = option_text_from_element(element, label)
        if not text:
            continue
        options[label] = {"text": text, "element": element}
        option_texts.append(text)

    if not options:
        return None

    dialog_text = read_visible_dialog_text(driver, dialog_xpath=dialog_xpath)
    question = extract_question_from_dialog_text(dialog_text, option_texts=option_texts)
    if not question:
        if logger:
            logger.warning("⚠️ 未能从题目弹窗中提取题干，跳过API答题")
        return None

    return PopupQuestionData(
        question=question,
        options=options,
        question_type=question_type,
    ).as_legacy_dict()


__all__ = [
    "PopupQuestionData",
    "build_popup_question_data",
    "extract_question_from_dialog_text",
    "option_text_from_element",
    "strip_option_prefix",
]

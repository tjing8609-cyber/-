import html as html_lib
import re
from dataclasses import dataclass

from quiz_popup_actions import visible_quiz_dialogs


OPTION_PREFIX_RE = re.compile(r"^\s*([A-Z])\s*[\.\u3001\uff09\)]?\s*(.*)$")
SKIP_QUESTION_LINES = {
    "AI随堂练习",
    "以下所有内容均由AI生成请注意甄别",
    "单选题",
    "多选题",
    "判断题",
    "提交作答",
    "提交",
    "确定",
    "确认",
    "完成",
    "继续",
    "关闭",
}
QUESTION_TYPE_MARKERS = ("单选题", "多选题", "判断题")
QUESTION_INFO_XPATHS = [
    ".//*[contains(@class,'question-info')]",
    ".//*[contains(@class,'richtext-container') and contains(@class,'question')]",
    ".//*[contains(@class,'ques-list')]//*[contains(@class,'row')]",
]


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


def html_to_text(markup):
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "\n", str(markup or ""))
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|span|button|header|footer)>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return html_lib.unescape(text)


def normalize_question_line(line):
    line = str(line or "").strip()
    line = re.sub(r"^\s*\d+\s*[\.\u3001\uff0e]\s*", "", line)
    line = re.sub(r"^[\[\u3010]?\s*(?:单选题|多选题|判断题)\s*[\]\u3011]?\s*", "", line)
    return line.strip()


def is_question_meta_line(line):
    normalized = normalize_question_line(line)
    if not normalized:
        return True
    if normalized in SKIP_QUESTION_LINES:
        return True
    if any(marker in normalized for marker in QUESTION_TYPE_MARKERS) and len(normalized) <= 12:
        return True
    if "AI生成" in normalized or "注意甄别" in normalized:
        return True
    return False


def extract_question_from_dialog_text(dialog_text, option_texts=None):
    option_texts = {str(text).strip() for text in (option_texts or []) if str(text).strip()}
    for raw_line in str(dialog_text or "").splitlines():
        line = normalize_question_line(raw_line)
        if not line:
            continue
        if line in option_texts or is_question_meta_line(line):
            continue
        if OPTION_PREFIX_RE.match(line):
            continue
        if len(line) >= 4:
            return line
    return ""


def _element_text(driver, element):
    try:
        text = (element.text or "").strip()
        if text:
            return text
    except Exception:
        pass
    for script in (
        "return arguments[0].innerText || '';",
        "return arguments[0].textContent || '';",
        "return arguments[0].innerHTML || '';",
    ):
        try:
            value = driver.execute_script(script, element)
            text = str(value or "").strip()
            if text:
                if "<" in text and ">" in text:
                    return html_to_text(text).strip()
                return text
        except Exception:
            continue
    return ""


def extract_question_from_dialog_dom(driver, dialog):
    for xpath in QUESTION_INFO_XPATHS:
        try:
            elements = dialog.find_elements("xpath", xpath)
        except Exception:
            elements = []
        for element in elements:
            text = _element_text(driver, element)
            question = extract_question_from_dialog_text(text)
            if question:
                return question
    return ""


def read_visible_dialog_text(driver, dialog_xpath=None):
    dialogs = visible_quiz_dialogs(driver, dialog_xpath)
    for dialog in dialogs:
        text = _element_text(driver, dialog)
        if text:
            return text
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

    dialogs = visible_quiz_dialogs(driver, dialog_xpath)
    question = ""
    if dialogs:
        question = extract_question_from_dialog_dom(driver, dialogs[0])
    dialog_text = read_visible_dialog_text(driver, dialog_xpath=dialog_xpath)
    if not question:
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
    "extract_question_from_dialog_dom",
    "html_to_text",
    "option_text_from_element",
    "strip_option_prefix",
]

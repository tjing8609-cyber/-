import re

from selenium.webdriver.common.by import By

from course_catalog import extract_catalog_title


UNWATCHED_MARKER_XPATH = ".//*[contains(@class, 'zhihuishu-weikaishi')]"
COMPLETED_MARKER_XPATH = (
    ".//*[contains(@class, 'zhihuishu-wancheng') "
    "or contains(@class, 'time_icofinish') "
    "or contains(@class, 'complete') "
    "or contains(@class, 'finish') "
    "or contains(@class, 'done')]"
)
PARTIAL_PROGRESS_RE = re.compile(r"(?<!\d)(0|[1-9]\d?)%")
FULL_PROGRESS_RE = re.compile(r"(?<!\d)100%")
COMPLETED_TEXT_MARKERS = ("已完成", "已观看", "已学完")


def _log(logger, level, message):
    if logger is None:
        return
    getattr(logger, level)(message)


def _safe_text(element):
    try:
        return element.text or ""
    except Exception:
        return ""


def video_title_from_text(text, max_length=50):
    return extract_catalog_title(text, max_length=max_length)


def element_context_chain(element, max_depth=2):
    elements = [element]
    current = element
    for _ in range(max_depth):
        try:
            current = current.find_element(By.XPATH, "./parent::*")
        except Exception:
            try:
                current = current.find_element(By.XPATH, "./..")
            except Exception:
                break
        elements.append(current)
    return elements


def _has_descendant(element, xpath):
    try:
        return bool(element.find_elements(By.XPATH, xpath))
    except Exception:
        return False


def has_unwatched_marker(element):
    return any(_has_descendant(candidate, UNWATCHED_MARKER_XPATH) for candidate in element_context_chain(element))


def has_completed_marker(element):
    return any(_has_descendant(candidate, COMPLETED_MARKER_XPATH) for candidate in element_context_chain(element))


def progress_state_from_text(text):
    text = text or ""
    if FULL_PROGRESS_RE.search(text):
        return "completed"
    if PARTIAL_PROGRESS_RE.search(text):
        return "partial"
    return "unknown"


def is_catalog_video_completed(element, logger=None):
    text = _safe_text(element)
    preview = text[:30] if text else "(无文本)"

    if has_unwatched_marker(element):
        _log(logger, "debug", f"  → 检测到未开始标记 - {preview}")
        return False

    progress_state = progress_state_from_text(text)
    if progress_state == "partial":
        _log(logger, "debug", f"  → 检测到部分观看进度，需要继续播放 - {preview}")
        return False
    if progress_state == "completed":
        _log(logger, "debug", f"  → 检测到100%进度 - {preview}")
        return True

    if has_completed_marker(element):
        _log(logger, "debug", f"  → 检测到完成标记 - {preview}")
        return True

    if any(marker in text for marker in COMPLETED_TEXT_MARKERS):
        _log(logger, "debug", f"  → 检测到完成文本 - {preview}")
        return True

    return False


__all__ = [
    "element_context_chain",
    "has_completed_marker",
    "has_unwatched_marker",
    "is_catalog_video_completed",
    "progress_state_from_text",
    "video_title_from_text",
]

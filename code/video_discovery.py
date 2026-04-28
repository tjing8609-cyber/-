from dataclasses import dataclass, field

from course_catalog import classify_catalog_text
from video_catalog import is_catalog_video_completed, video_title_from_text


SKIP_TEXT_MARKERS = [
    ".pptx",
    ".ppt",
    ".pdf",
    "作业",
    "见面课",
    "课程问答",
    "课程表",
    "成绩分析",
    "课程资料",
    "平时测试",
]


@dataclass
class VideoDiscoveryResult:
    unwatched: list = field(default_factory=list)
    watched: list = field(default_factory=list)
    skipped: int = 0


def _log(logger, level, message):
    if logger is None:
        return
    getattr(logger, level)(message)


def safe_element_text(element):
    try:
        return element.text or ""
    except Exception:
        return ""


def is_interactable(element):
    try:
        return element.is_displayed() and element.is_enabled()
    except Exception:
        return False


def is_skippable_video_text(text, require_mp4=False):
    normalized = text or ""
    lowered = normalized.lower()
    if require_mp4 and ".mp4" not in lowered:
        return True, "non-mp4 item"
    for marker in SKIP_TEXT_MARKERS:
        if marker.lower() in lowered or marker in normalized:
            return True, f"skip marker: {marker}"
    return False, ""


def clickable_video_element(element, prefer_inner_link=False):
    if not prefer_inner_link:
        return element
    try:
        tag_name = (element.tag_name or "").lower()
    except Exception:
        tag_name = ""
    if tag_name == "a":
        return element
    try:
        link = element.find_element("xpath", ".//a")
        if is_interactable(link):
            return link
    except Exception:
        pass
    return element


def add_watched_record(watched, text):
    title = video_title_from_text(text, max_length=50)
    if not title:
        return
    if not any(item.get("title") == title for item in watched):
        watched.append({"text": text[:100], "title": title})


def scan_video_candidates(
    elements,
    completed_texts=None,
    logger=None,
    require_mp4=False,
    prefer_inner_link=False,
    record_watched=True,
):
    completed_texts = set(completed_texts or [])
    result = VideoDiscoveryResult()

    for index, element in enumerate(elements or []):
        try:
            text = safe_element_text(element).strip()
            if not text or len(text) < 3:
                result.skipped += 1
                continue

            classification = classify_catalog_text(text)
            if not classification.is_video:
                _log(logger, "debug", f"  → 跳过：{classification.reason} ({text[:30]}...)")
                result.skipped += 1
                continue

            skippable, reason = is_skippable_video_text(text, require_mp4=require_mp4)
            if skippable:
                _log(logger, "debug", f"  → 跳过：{reason} ({text[:30]}...)")
                result.skipped += 1
                continue

            if is_catalog_video_completed(element, logger=logger):
                _log(logger, "debug", f"  → 跳过：已完成 ({text[:30]}...)")
                if record_watched:
                    add_watched_record(result.watched, text)
                result.skipped += 1
                continue

            if text in completed_texts:
                _log(logger, "debug", f"  → 跳过：已记录 ({text[:30]}...)")
                result.skipped += 1
                continue

            target = clickable_video_element(element, prefer_inner_link=prefer_inner_link)
            if is_interactable(target):
                result.unwatched.append({"element": target, "text": text[:100]})
                _log(logger, "info", f"  → ✅ 找到未观看视频: {text[:50]}...")
            else:
                result.skipped += 1
        except Exception as e:
            _log(logger, "debug", f"处理视频元素 {index + 1} 时出错: {e}")
            result.skipped += 1

    return result


def dedupe_elements_by_text(elements, min_length=3):
    unique = []
    seen = set()
    for element in elements or []:
        text = safe_element_text(element).strip()
        if text and len(text) >= min_length and text not in seen:
            seen.add(text)
            unique.append(element)
    return unique


__all__ = [
    "VideoDiscoveryResult",
    "clickable_video_element",
    "dedupe_elements_by_text",
    "is_skippable_video_text",
    "scan_video_candidates",
]

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Read-only observer helpers for the Hybrid Agent foundation."""

from dataclasses import dataclass
import html as html_lib
import re
from typing import Any, Dict, List, Optional

from agent.schemas import AgentEvent, ObservationFrame, StateSnapshot, current_timestamp, safe_dict, safe_list


@dataclass
class ObserverOptions:
    html_digest_limit: int = 1000
    title_limit: int = 200
    url_limit: int = 500
    max_dialogs: int = 10
    max_elements_digest: int = 0
    include_html_digest: bool = True


def safe_getattr(obj: Any, name: str, default: Any = "") -> Any:
    if obj is None:
        return default
    try:
        return getattr(obj, name)
    except Exception:
        return default


def safe_call(obj: Any, method_name: str, default: Any = None, *args, **kwargs) -> Any:
    if obj is None:
        return default
    try:
        method = getattr(obj, method_name)
    except Exception:
        return default
    if not callable(method):
        return default
    try:
        return method(*args, **kwargs)
    except Exception:
        return default


def _limit_value(limit: Any, default: int = 500) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    return max(0, value)


def safe_string(value: Any, limit: int = 500) -> str:
    if value is None:
        return ""
    try:
        text = str(value)
    except Exception:
        return ""
    text = text.strip()
    max_len = _limit_value(limit)
    if max_len and len(text) > max_len:
        return text[:max_len]
    if max_len == 0:
        return ""
    return text


def html_to_digest(html: Any, limit: int = 1000) -> str:
    text = safe_string(html, limit=0 if limit == 0 else max(_limit_value(limit), 1_000_000))
    if not text:
        return ""
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    max_len = _limit_value(limit, default=1000)
    return text[:max_len] if max_len else ""


def _options(options: Optional[ObserverOptions]) -> ObserverOptions:
    return options if isinstance(options, ObserverOptions) else ObserverOptions()


def extract_basic_driver_info(driver: Any, options: Optional[ObserverOptions] = None) -> Dict[str, str]:
    opts = _options(options)
    page_source = safe_getattr(driver, "page_source", "")
    return {
        "url": safe_string(safe_getattr(driver, "current_url", ""), opts.url_limit),
        "title": safe_string(safe_getattr(driver, "title", ""), opts.title_limit),
        "page_text_digest": html_to_digest(page_source, opts.html_digest_limit) if opts.include_html_digest else "",
    }


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return bool(value)


def _video_value(video_state: Any, key: str, default: Any = None) -> Any:
    if isinstance(video_state, dict):
        return video_state.get(key, default)
    return safe_getattr(video_state, key, default)


def normalize_video_state(video_state: Any) -> Dict[str, Any]:
    present = _as_bool(_video_value(video_state, "present", False), False)
    duration = _as_float(_video_value(video_state, "duration", 0.0), 0.0)
    current_time = _as_float(
        _video_value(video_state, "current_time", _video_value(video_state, "currentTime", 0.0)),
        0.0,
    )
    paused = _as_bool(_video_value(video_state, "paused", True), True)
    ended = _as_bool(_video_value(video_state, "ended", False), False)

    playing_raw = _video_value(video_state, "playing", None)
    completed_raw = _video_value(video_state, "completed", None)
    playing = _as_bool(playing_raw, present and not paused and not ended)
    completed = _as_bool(
        completed_raw,
        ended or (present and duration > 0 and current_time >= max(0.0, duration - 5.0)),
    )

    return {
        "present": present,
        "duration": duration,
        "current_time": current_time,
        "paused": paused,
        "ended": ended,
        "playing": playing,
        "completed": completed,
    }


def _dialog_to_dict(dialog: Any) -> Dict[str, Any]:
    if isinstance(dialog, dict):
        text = dialog.get("text", dialog.get("title", ""))
        role = dialog.get("role", "")
        visible = dialog.get("visible", dialog.get("displayed", True))
    else:
        text = safe_getattr(dialog, "text", "")
        if not text:
            text = safe_getattr(dialog, "title", "")
        role = safe_getattr(dialog, "role", "")
        visible = safe_getattr(dialog, "visible", safe_getattr(dialog, "displayed", True))
        is_displayed = safe_call(dialog, "is_displayed", default=None)
        if is_displayed is not None:
            visible = is_displayed

    return {
        "text": safe_string(text, 500),
        "role": safe_string(role, 80),
        "visible": _as_bool(visible, True),
    }


def normalize_dialogs(dialogs: Any, max_dialogs: int = 10) -> List[Dict[str, Any]]:
    if dialogs is None:
        items = []
    elif isinstance(dialogs, (list, tuple)):
        items = list(dialogs)
    else:
        items = [dialogs]

    result = []
    limit = _limit_value(max_dialogs, default=10)
    for item in items[:limit]:
        try:
            result.append(_dialog_to_dict(item))
        except Exception:
            continue
    return result


def infer_state_from_digest(
    url: str,
    title: str,
    page_text_digest: str,
    video_state: Any = None,
    dialogs: Any = None,
) -> StateSnapshot:
    normalized_video = normalize_video_state(video_state)
    normalized_dialogs = normalize_dialogs(dialogs)
    text = " ".join([safe_string(url, 1000), safe_string(title, 500), safe_string(page_text_digest, 2000)])
    dialog_text = " ".join(safe_string(item.get("text", ""), 500) for item in normalized_dialogs)
    combined = f"{text} {dialog_text}"

    has_video = bool(normalized_video["present"])
    has_dialog = bool(normalized_dialogs)
    has_captcha = any(marker in combined.lower() for marker in ["验证码", "captcha", "人机", "滑块", "验证"])
    has_course_markers = any(marker in combined for marker in ["课程目录", "章节", "继续学习", "开始学习", "课程"])
    has_quiz_markers = any(marker in combined for marker in ["题目", "单选题", "多选题", "判断题", "AI随堂练习"])

    overlays = []
    if has_captcha:
        overlays.append("captcha")
    if has_dialog:
        overlays.append("common_dialog")
    if has_quiz_markers and has_dialog:
        overlays.append("quiz_popup")

    if has_video:
        primary_state = "video_page"
        task_phase = "watch_video" if not normalized_video["completed"] else "done"
        confidence = 0.85
    elif has_quiz_markers:
        primary_state = "quiz_page"
        task_phase = "answer_quiz"
        confidence = 0.7
    elif has_captcha or ("登录" in combined or "密码" in combined):
        primary_state = "login"
        task_phase = "login"
        confidence = 0.65
    elif has_course_markers:
        primary_state = "course_catalog" if ("课程目录" in combined or "章节" in combined) else "course_home"
        task_phase = "navigate_course"
        confidence = 0.65
    else:
        primary_state = "unknown"
        task_phase = "unknown"
        confidence = 0.0

    flags = {
        "has_video": has_video,
        "video_playing": bool(normalized_video["playing"]),
        "video_completed": bool(normalized_video["completed"]),
        "has_dialog": has_dialog,
        "has_captcha": has_captcha,
        "has_course_markers": has_course_markers,
        "has_clickable_candidates": False,
    }
    reason = "inferred from read-only digest" if primary_state != "unknown" else "no reliable markers"
    return StateSnapshot(
        primary_state=primary_state,
        overlays=overlays,
        flags=flags,
        task_phase=task_phase,
        confidence=confidence,
        reason=reason,
    )


class AgentObserver:
    def __init__(self, options: Optional[ObserverOptions] = None):
        self.options = _options(options)

    def observe(
        self,
        driver: Any = None,
        *,
        mode: str = "",
        course_name: str = "",
        video_state: Any = None,
        dialogs: Any = None,
        state: Any = None,
        screenshot_path: str = "",
        html_snapshot_path: str = "",
        som_image_path: str = "",
        notes: str = "",
    ) -> ObservationFrame:
        info = extract_basic_driver_info(driver, self.options)
        normalized_video = normalize_video_state(video_state)
        normalized_dialogs = normalize_dialogs(dialogs, self.options.max_dialogs)

        if state is None:
            snapshot = infer_state_from_digest(
                info["url"],
                info["title"],
                info["page_text_digest"],
                video_state=normalized_video,
                dialogs=normalized_dialogs,
            )
        else:
            snapshot = state if isinstance(state, StateSnapshot) else StateSnapshot.from_dict(state)

        return ObservationFrame(
            url=info["url"],
            title=info["title"],
            mode=safe_string(mode, 100),
            course_name=safe_string(course_name, 300),
            timestamp=current_timestamp(),
            state=snapshot,
            video_state=normalized_video,
            dialogs=normalized_dialogs,
            elements_digest=[],
            screenshot_path=safe_string(screenshot_path, 1000),
            html_snapshot_path=safe_string(html_snapshot_path, 1000),
            som_image_path=safe_string(som_image_path, 1000),
            notes=safe_string(notes, 1000),
        )


def observe_to_event(
    observation: ObservationFrame,
    *,
    run_id: str = "",
    step_index: int = 0,
    event_type: str = "observe",
    account_file: str = "",
    last_action: Optional[Dict[str, Any]] = None,
    error: str = "",
    notes: str = "",
) -> AgentEvent:
    frame = observation if isinstance(observation, ObservationFrame) else ObservationFrame.from_dict(observation)
    return AgentEvent(
        event_type=event_type,
        run_id=run_id,
        step_index=step_index,
        mode=frame.mode,
        account_file=account_file,
        url=frame.url,
        state=frame.state,
        observation=frame,
        last_action=safe_dict(last_action),
        error=error,
        notes=notes or frame.notes,
    )


__all__ = [
    "AgentObserver",
    "ObserverOptions",
    "extract_basic_driver_info",
    "html_to_digest",
    "infer_state_from_digest",
    "normalize_dialogs",
    "normalize_video_state",
    "observe_to_event",
    "safe_call",
    "safe_getattr",
    "safe_string",
]

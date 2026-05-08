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


LOGIN_MARKERS = ["请登录", "登录", "账号", "手机号", "密码", "验证码", "login", "password"]
COURSE_HOME_MARKERS = ["我的课程", "课程首页", "课程封面", "进入学习", "开始学习", "继续学习", "学习进度"]
COURSE_CATALOG_MARKERS = [
    "课程目录",
    "章节",
    "小节",
    "目录",
    "已学",
    "未学",
    "继续学习",
    "开始学习",
    "第一章",
    "第二章",
    "第三章",
    "第四章",
    "第一节",
    "第二节",
]
VIDEO_URL_MARKERS = ["studyvideo", "video", "learn", "study"]
VIDEO_TEXT_MARKERS = ["播放", "暂停", "倍速", "清晰度", "下一节", "学习时长", "视频", "video", "player"]
QUIZ_MARKERS = [
    "题目",
    "单选题",
    "多选题",
    "判断题",
    "问答题",
    "考试",
    "测试",
    "课程测试",
    "章节测试",
    "提交答案",
    "交卷",
    "上一题",
    "下一题",
    "请选择",
    "quiz",
    "exam",
    "AI随堂练习",
]
COMPLETED_MARKERS = ["已完成", "学习完成", "课程完成", "观看完成", "完成学习", "completed"]
ERROR_MARKERS = [
    "系统错误",
    "页面错误",
    "出现错误",
    "发生错误",
    "异常",
    "加载失败",
    "网络异常",
    "服务器错误",
    "页面不存在",
    "404",
    "500",
    "timeout",
    "error",
    "failed",
]
CAPTCHA_MARKERS = ["验证码", "人机验证", "安全验证", "滑块", "滑动验证", "captcha", "verify", "robot"]
COMMON_DIALOG_MARKERS = ["温馨提示", "提示", "知道了", "我知道了", "关闭", "取消", "确定", "确认"]
QUIZ_POPUP_MARKERS = ["随堂测验", "弹题", "检测题", "课堂检测", "本节测试", "题目", "请选择", "AI随堂练习"]
LOADING_MARKERS = ["加载中", "正在加载", "请稍候", "loading", "spinner"]
CONFIRM_MARKERS = ["确认提交", "确认交卷", "是否提交", "是否关闭", "确定提交", "确定交卷"]
ACTION_MARKERS = ["开始学习", "继续学习", "提交", "确认", "关闭", "播放", "下一节", "进入学习"]


def normalize_probe_text(*parts: Any) -> str:
    values = []
    for part in parts:
        text = safe_string(part, 12000)
        if text:
            values.append(text)
    return re.sub(r"\s+", " ", " ".join(values)).strip()


def contains_any(text: str, markers: List[str]) -> List[str]:
    normalized = safe_string(text, 8000).lower()
    matches = []
    for marker in markers:
        value = safe_string(marker, 120)
        if value and value.lower() in normalized and value not in matches:
            matches.append(value)
    return matches


def count_markers(text: str, markers: List[str]) -> int:
    return len(contains_any(text, markers))


def _reason(label: str, matches: List[str]) -> str:
    if not matches:
        return ""
    return f"matched {label}: {', '.join(matches[:3])}"


def detect_overlays(
    text: str,
    dialogs: List[Dict[str, Any]],
    quiz_matches: List[str],
) -> tuple:
    captcha_matches = contains_any(text, CAPTCHA_MARKERS)
    common_matches = contains_any(text, COMMON_DIALOG_MARKERS)
    quiz_popup_matches = contains_any(text, QUIZ_POPUP_MARKERS)
    loading_matches = contains_any(text, LOADING_MARKERS)
    confirm_matches = contains_any(text, CONFIRM_MARKERS)

    overlays = []
    if captcha_matches:
        overlays.append("captcha")
    if dialogs or (common_matches and not confirm_matches):
        overlays.append("common_dialog")
    strong_quiz_popup_matches = [
        marker for marker in quiz_popup_matches if marker not in {"题目", "请选择"}
    ]
    if strong_quiz_popup_matches or (quiz_matches and (dialogs or contains_any(text, ["检测", "随堂", "弹题"]))):
        overlays.append("quiz_popup")
    if loading_matches:
        overlays.append("loading")
    if confirm_matches:
        overlays.append("confirm_dialog")

    overlay_matches = {
        "captcha": captcha_matches,
        "common_dialog": common_matches,
        "quiz_popup": quiz_popup_matches,
        "loading": loading_matches,
        "confirm_dialog": confirm_matches,
    }
    return overlays, overlay_matches


def detect_task_phase(primary_state: str, overlays: List[str]) -> str:
    if "quiz_popup" in overlays:
        return "handle_popup"
    if primary_state == "login":
        return "login"
    if primary_state in {"course_home", "course_catalog"}:
        return "navigate_course"
    if primary_state == "video_page":
        return "watch_video"
    if primary_state == "quiz_page":
        return "answer_quiz"
    if primary_state == "completed":
        return "done"
    if primary_state == "error":
        return "error"
    return "unknown"


def infer_state_from_digest(
    url: str,
    title: str,
    page_text_digest: str,
    video_state: Any = None,
    dialogs: Any = None,
) -> StateSnapshot:
    normalized_video = normalize_video_state(video_state)
    normalized_dialogs = normalize_dialogs(dialogs)
    url_text = safe_string(url, 1000)
    text = normalize_probe_text(url_text, title, page_text_digest)
    dialog_text = " ".join(safe_string(item.get("text", ""), 500) for item in normalized_dialogs)
    combined = normalize_probe_text(text, dialog_text)

    login_matches = contains_any(combined, LOGIN_MARKERS)
    course_home_matches = contains_any(combined, COURSE_HOME_MARKERS)
    course_catalog_matches = contains_any(combined, COURSE_CATALOG_MARKERS)
    video_text_matches = contains_any(combined, VIDEO_TEXT_MARKERS)
    video_url_matches = contains_any(url_text, VIDEO_URL_MARKERS)
    quiz_matches = contains_any(combined, QUIZ_MARKERS)
    completed_matches = contains_any(combined, COMPLETED_MARKERS)
    error_matches = contains_any(combined, ERROR_MARKERS)
    action_matches = contains_any(combined, ACTION_MARKERS)
    overlays, overlay_matches = detect_overlays(combined, normalized_dialogs, quiz_matches)

    video_completed = bool(normalized_video["completed"] or completed_matches)
    has_video = bool(normalized_video["present"] or video_text_matches or video_url_matches)
    has_captcha = bool(overlay_matches["captcha"])
    has_quiz_markers = bool(quiz_matches)
    has_course_markers = bool(course_home_matches or course_catalog_matches)
    has_error_markers = bool(error_matches)
    has_loading_markers = bool(overlay_matches["loading"])
    has_confirm_markers = bool(overlay_matches["confirm_dialog"])
    has_dialog = bool(
        normalized_dialogs
        or overlay_matches["common_dialog"]
        or has_confirm_markers
        or has_captcha
        or "quiz_popup" in overlays
    )
    has_clickable_candidates = bool(action_matches)

    if has_error_markers:
        primary_state = "error"
        confidence = 0.85 if len(error_matches) == 1 else 0.9
        reason = _reason("error markers", error_matches)
    elif video_completed:
        primary_state = "completed"
        confidence = 0.92 if normalized_video["completed"] else 0.82
        reason = "matched video_state.completed" if normalized_video["completed"] else _reason("completed markers", completed_matches)
    elif normalized_video["present"]:
        primary_state = "video_page"
        confidence = 0.94
        reason = "matched video_state.present"
    elif len(quiz_matches) >= 2 or any(marker in quiz_matches for marker in ["提交答案", "交卷"]):
        primary_state = "quiz_page"
        confidence = 0.82 if len(quiz_matches) >= 3 else 0.75
        reason = _reason("quiz markers", quiz_matches)
    elif len(login_matches) >= 2 or any(marker in login_matches for marker in ["请登录", "login", "password"]):
        primary_state = "login"
        confidence = 0.82 if len(login_matches) >= 3 else 0.75
        reason = _reason("login markers", login_matches)
    elif len(course_catalog_matches) >= 2 or any(marker in course_catalog_matches for marker in ["课程目录", "章节", "目录"]):
        primary_state = "course_catalog"
        confidence = 0.76 if len(course_catalog_matches) >= 3 else 0.68
        reason = _reason("course catalog markers", course_catalog_matches)
    elif course_home_matches:
        primary_state = "course_home"
        confidence = 0.7 if len(course_home_matches) >= 2 else 0.62
        reason = _reason("course home markers", course_home_matches)
    elif video_text_matches:
        primary_state = "video_page"
        confidence = 0.68 if len(video_text_matches) >= 2 else 0.58
        reason = _reason("video markers", video_text_matches)
    elif video_url_matches:
        primary_state = "video_page"
        confidence = 0.55
        reason = _reason("video url markers", video_url_matches)
    else:
        primary_state = "unknown"
        confidence = 0.0
        reason = "no reliable markers"

    task_phase = detect_task_phase(primary_state, overlays)

    flags = {
        "has_video": has_video,
        "video_playing": bool(normalized_video["playing"]),
        "video_completed": video_completed,
        "has_dialog": has_dialog,
        "has_captcha": has_captcha,
        "has_course_markers": has_course_markers,
        "has_quiz_markers": has_quiz_markers,
        "has_error_markers": has_error_markers,
        "has_loading_markers": has_loading_markers,
        "has_confirm_markers": has_confirm_markers,
        "has_clickable_candidates": has_clickable_candidates,
    }
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
            page_text_digest=info["page_text_digest"],
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

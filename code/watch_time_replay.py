"""Helpers for replaying completed videos to satisfy daily watch time."""

import time
from dataclasses import dataclass

from selenium.webdriver.common.action_chains import ActionChains

from video_playback import VideoCompletionMonitor


REPLAY_WATCHED_VIDEOS_KEY = "replay_watched_videos"


@dataclass
class ReplayLoopResult:
    reached_limit: bool = False
    loops_completed: int = 0
    reason: str = ""


def is_replay_watched_enabled(config):
    if not isinstance(config, dict):
        return False
    value = config.get(REPLAY_WATCHED_VIDEOS_KEY, False)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return bool(value)


def coerce_watch_minutes(value, default=0.0):
    try:
        minutes = float(value or 0)
    except (TypeError, ValueError):
        return float(default)
    return max(0.0, minutes)


def click_video_entry(driver, video_info, logger=None):
    element = (video_info or {}).get("element")
    if element is None:
        _log(logger, "warning", "No video entry element is available for replay mode")
        return False

    try:
        element.click()
        _log(logger, "info", "Replay mode clicked the first video entry")
        return True
    except Exception as exc:
        _log(logger, "debug", f"Direct video entry click failed: {exc}")

    try:
        actions = ActionChains(driver)
        actions.move_to_element(element)
        actions.click()
        actions.perform()
        _log(logger, "info", "Replay mode clicked the first video entry with ActionChains")
        return True
    except Exception as exc:
        _log(logger, "error", f"Failed to click replay video entry: {exc}")
        return False


def run_replay_loop(
    player,
    click_replay,
    quiz_handler=None,
    sleep_func=time.sleep,
    check_interval_seconds=10,
    max_single_loop_seconds=4 * 60 * 60,
):
    """Replay the current video until the player's configured watch limit is met."""
    logger = getattr(player, "logger", None)
    max_watch_minutes = coerce_watch_minutes(getattr(player, "max_watch_minutes", 0))
    if max_watch_minutes <= 0:
        _log(logger, "error", "Replay mode requires max_watch_minutes > 0 to avoid an endless run")
        return ReplayLoopResult(False, 0, "missing_time_limit")

    loops_completed = 0
    video_start_total_time = _safe_number(getattr(player, "total_watch_time_seconds", 0))
    video_start_progress = _safe_call(player.get_video_progress, 0.0)
    last_counted_video_progress = video_start_progress
    current_video_played_seconds = 0.0
    completion_monitor = _new_completion_monitor()
    elapsed_in_loop = 0

    _log(logger, "info", f"Replay mode active: target {max_watch_minutes:g} minutes")

    while elapsed_in_loop < max_single_loop_seconds:
        if quiz_handler is not None:
            _safe_call(quiz_handler, None)

        current_progress = _safe_call(player.get_video_progress, 0.0)
        current_video_played_seconds, last_counted_video_progress = (
            player.update_current_video_played_seconds(
                current_video_played_seconds,
                current_progress,
                last_counted_video_progress,
            )
        )

        video_info = read_current_video_info(getattr(player, "driver", None))
        video_position = max(current_progress, video_info.get("current_time", 0.0))
        duration = video_info.get("duration", 0.0)
        completion_decision = completion_monitor.update(
            present=video_info.get("present", False),
            duration=duration,
            current_time=video_position,
            ended=video_info.get("ended", False),
        )

        if _has_reached_limit(
            player,
            video_position,
            video_start_total_time,
            video_start_progress,
            current_video_played_seconds,
        ):
            _commit_and_log_limit(
                player,
                video_position,
                video_start_total_time,
                video_start_progress,
                current_video_played_seconds,
                loops_completed,
            )
            return ReplayLoopResult(True, loops_completed, "time_limit")

        if completion_decision.completed:
            current_video_played_seconds, last_counted_video_progress = (
                player.update_current_video_played_seconds(
                    current_video_played_seconds,
                    video_position,
                    last_counted_video_progress,
                )
            )
            if completion_decision.reason == "rolled_back_after_near_end" and duration > 0:
                current_video_played_seconds = max(
                    current_video_played_seconds,
                    player.get_current_video_played_seconds(duration, video_start_progress),
                )
                video_position = duration

            player.commit_current_video_watch_time(
                video_position,
                video_start_total_time,
                video_start_progress,
                current_video_played_seconds,
            )
            loops_completed += 1
            _log(
                logger,
                "info",
                f"Replay loop {loops_completed} completed; watched time: "
                f"{player.format_watch_time_text(getattr(player, 'total_watch_time_seconds', 0))}",
            )

            if _has_reached_limit(player, 0, getattr(player, "total_watch_time_seconds", 0), 0, 0):
                player.log_max_watch_time_reached(loops_completed)
                return ReplayLoopResult(True, loops_completed, "time_limit")

            if not click_replay():
                _log(logger, "warning", "Replay click did not report success; trying playback recovery")
            _safe_call(getattr(player, "ensure_video_playing", None), None)
            _safe_wait(getattr(player, "smart_wait", None), 2)

            video_start_total_time = _safe_number(getattr(player, "total_watch_time_seconds", 0))
            video_start_progress = _safe_call(player.get_video_progress, 0.0)
            last_counted_video_progress = video_start_progress
            current_video_played_seconds = 0.0
            completion_monitor = _new_completion_monitor()
            elapsed_in_loop = 0
            continue

        if not _safe_call(getattr(player, "is_video_playing", None), True):
            _log(logger, "warning", "Replay video appears paused; trying to resume")
            _safe_call(getattr(player, "ensure_video_playing", None), None)

        total_seconds = player.get_session_watch_seconds(
            video_position,
            video_start_total_time,
            video_start_progress,
            current_video_played_seconds,
        )
        _log(
            logger,
            "info",
            f"Replay progress: video={video_position:.0f}s duration={duration:.0f}s "
            f"watched={player.format_watch_time_text(total_seconds)}",
        )

        sleep_func(check_interval_seconds)
        elapsed_in_loop += check_interval_seconds

    player.commit_current_video_watch_time(
        _safe_call(player.get_video_progress, 0.0),
        video_start_total_time,
        video_start_progress,
        current_video_played_seconds,
    )
    _log(logger, "warning", "Replay loop timed out before detecting video completion")
    return ReplayLoopResult(False, loops_completed, "loop_timeout")


def read_current_video_info(driver):
    if driver is None:
        return {"present": False, "duration": 0.0, "current_time": 0.0, "ended": False}
    try:
        data = driver.execute_script(
            """
            var video = document.querySelector('video');
            if (!video) {
              return {present: false};
            }
            return {
              present: true,
              duration: Number(video.duration || 0),
              currentTime: Number(video.currentTime || 0),
              ended: Boolean(video.ended)
            };
            """
        )
    except Exception:
        data = None
    if not data:
        return {"present": False, "duration": 0.0, "current_time": 0.0, "ended": False}
    return {
        "present": bool(data.get("present")),
        "duration": _safe_number(data.get("duration")),
        "current_time": _safe_number(data.get("currentTime")),
        "ended": bool(data.get("ended", False)),
    }


def _new_completion_monitor():
    return VideoCompletionMonitor(
        completion_percent=99.8,
        rollover_percent=99.0,
        near_end_seconds=0.5,
    )


def _has_reached_limit(player, current_progress, start_total, start_progress, played_seconds):
    return player.has_reached_max_watch_time(
        current_progress,
        start_total,
        start_progress,
        played_seconds,
    )


def _commit_and_log_limit(player, current_progress, start_total, start_progress, played_seconds, loops_completed):
    player.commit_current_video_watch_time(
        current_progress,
        start_total,
        start_progress,
        played_seconds,
    )
    player.log_max_watch_time_reached(loops_completed)


def _safe_call(callback, default=None):
    if callback is None:
        return default
    try:
        result = callback()
    except Exception:
        return default
    return default if result is None else result


def _safe_wait(wait_func, seconds):
    if wait_func is None:
        return
    try:
        wait_func(seconds)
    except Exception:
        return


def _safe_number(value):
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _log(logger, level, message):
    if logger is None:
        return
    getattr(logger, level)(message)


__all__ = [
    "REPLAY_WATCHED_VIDEOS_KEY",
    "ReplayLoopResult",
    "click_video_entry",
    "coerce_watch_minutes",
    "is_replay_watched_enabled",
    "read_current_video_info",
    "run_replay_loop",
]

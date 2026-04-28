#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Shared video playback state helpers."""

import random
from dataclasses import dataclass

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By


@dataclass
class VideoState:
    present: bool = False
    duration: float = 0.0
    current_time: float = 0.0
    paused: bool = True
    ended: bool = False

    @property
    def playing(self):
        return self.present and not self.paused and not self.ended

    @property
    def completed(self):
        if not self.present:
            return False
        if self.ended:
            return True
        return self.duration > 0 and self.current_time >= max(0, self.duration - 5)


@dataclass
class ProgressDecision:
    progress: float
    stalled: bool = False
    recovered: bool = False
    stall_count: int = 0
    should_recover: bool = False


class ProgressStallMonitor:
    def __init__(self, min_delta=1.0, recover_after=3, near_end_percent=95.0):
        self.min_delta = min_delta
        self.recover_after = recover_after
        self.near_end_percent = near_end_percent
        self.last_progress = None
        self.stall_count = 0

    def update(self, progress, progress_percent=0.0):
        progress = float(progress or 0)
        if self.last_progress is None:
            self.last_progress = progress
            return ProgressDecision(progress=progress, stall_count=0)

        stalled = abs(progress - self.last_progress) < self.min_delta
        recovered = False
        should_recover = False

        if stalled:
            self.stall_count += 1
            reported_stall_count = self.stall_count
            should_recover = (
                self.stall_count >= self.recover_after
                and float(progress_percent or 0) < self.near_end_percent
            )
            if should_recover:
                self.stall_count = 0
        else:
            recovered = self.stall_count > 0
            self.stall_count = 0
            reported_stall_count = 0

        self.last_progress = progress
        return ProgressDecision(
            progress=progress,
            stalled=stalled,
            recovered=recovered,
            stall_count=reported_stall_count,
            should_recover=should_recover,
        )


def _log(logger, level, message):
    if logger is None:
        return
    getattr(logger, level)(message)


def get_video_state(driver, logger=None):
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
              paused: Boolean(video.paused),
              ended: Boolean(video.ended)
            };
            """
        )
        if not data:
            return VideoState()
        return VideoState(
            present=bool(data.get("present")),
            duration=float(data.get("duration") or 0),
            current_time=float(data.get("currentTime") or 0),
            paused=bool(data.get("paused", True)),
            ended=bool(data.get("ended", False)),
        )
    except Exception as exc:
        _log(logger, "debug", f"获取视频状态失败: {exc}")
        return VideoState()


def get_video_duration(driver, logger=None):
    state = get_video_state(driver, logger=logger)
    return state.duration if state.duration > 0 else None


def get_video_progress(driver, logger=None):
    return get_video_state(driver, logger=logger).current_time


def is_video_playing(driver, logger=None):
    return get_video_state(driver, logger=logger).playing


def is_video_completed(driver, logger=None):
    return get_video_state(driver, logger=logger).completed


def click_video_center(driver, logger=None, offset_min=-20, offset_max=20, success_message="已点击视频中央"):
    try:
        video = driver.find_element(By.XPATH, "//video")
        size = video.size
        width = size["width"]
        height = size["height"]
        offset_x = random.randint(offset_min, offset_max)
        offset_y = random.randint(offset_min, offset_max)

        actions = ActionChains(driver)
        actions.move_to_element_with_offset(video, offset_x, offset_y)
        actions.click()
        actions.perform()

        _log(logger, "info", f"{success_message}(偏移: {width // 2 + offset_x}, {height // 2 + offset_y})")
        return True
    except Exception as exc:
        _log(logger, "warning", f"点击视频中央失败: {exc}")
        return False

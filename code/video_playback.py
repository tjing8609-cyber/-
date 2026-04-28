#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Shared video playback state helpers."""

import random
from dataclasses import dataclass

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from element_actions import click_element


PLAY_BUTTON_SELECTORS = [
    "//div[contains(@class, 'vjs-big-play-button')]",
    "//button[contains(@class, 'play-btn')]",
    "//div[contains(@class, 'play-btn')]",
]

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


def _wait(wait_func, seconds):
    if wait_func is None:
        return
    wait_func(seconds)


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


def click_video_center(
    driver,
    logger=None,
    offset_min=-20,
    offset_max=20,
    success_message="已点击视频中央",
    video_xpath="//video",
):
    try:
        video = driver.find_element(By.XPATH, video_xpath)
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


def click_visible_play_button(driver, logger=None, wait_func=None):
    for selector in PLAY_BUTTON_SELECTORS:
        try:
            buttons = driver.find_elements(By.XPATH, selector)
            for button in buttons:
                if not button.is_displayed():
                    continue
                _log(logger, "info", f"找到可见的播放按钮: {selector}")
                if click_element(driver, button, logger=logger, wait_func=wait_func, wait_seconds=1, scroll=False):
                    _log(logger, "info", "✅ 点击了播放按钮")
                    return True
        except Exception:
            continue
    return False


def start_video_playback(driver, logger=None, wait_func=None, video_xpath="//video"):
    _log(logger, "info", "尝试点击视频中央区域启动播放...")
    clicked_any = False

    if click_video_center(
        driver,
        logger=logger,
        offset_min=-30,
        offset_max=30,
        success_message="✅ 成功点击视频中央区域",
        video_xpath=video_xpath,
    ):
        clicked_any = True
        _wait(wait_func, 2)

    if click_visible_play_button(driver, logger=logger, wait_func=wait_func):
        clicked_any = True

    _log(logger, "info", "使用ActionChains点击视频中央启动播放")
    if click_video_center(
        driver,
        logger=logger,
        offset_min=-30,
        offset_max=30,
        success_message="✅ 已点击视频中央",
        video_xpath=video_xpath,
    ):
        clicked_any = True

    _wait(wait_func, 2)
    _log(logger, "info", "✅ 视频启动流程完成")
    return clicked_any

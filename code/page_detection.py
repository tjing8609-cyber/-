#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Shared browser page detection helpers."""

from selenium.webdriver.common.by import By


COURSE_READY_MARKERS = ["继续学习", "开始学习", "学习进度", "章节", "课程目录", "视频"]
ENTER_STUDY_TEXTS = ["继续学习", "开始学习", "进入学习", "去学习"]
COMMON_DIALOG_BUTTON_TEXTS = ["同意", "确认", "关闭", "知道了"]


def _log(logger, level, message):
    if logger is None:
        return
    getattr(logger, level)(message)


def _wait(wait_func, seconds):
    if wait_func is None:
        return
    wait_func(seconds)


def visible_elements(driver, xpath):
    try:
        return [element for element in driver.find_elements(By.XPATH, xpath) if element.is_displayed()]
    except Exception:
        return []


def page_source_contains_any(driver, markers):
    try:
        page_source = driver.page_source or ""
        return any(marker in page_source for marker in markers)
    except Exception:
        return False


def is_video_present(driver):
    try:
        return bool(driver.find_elements(By.TAG_NAME, "video"))
    except Exception:
        return False


def is_course_page_ready(driver):
    try:
        current_url = (driver.current_url or "").lower()
        if "studyvideo" in current_url or "study" in current_url:
            return True
        if is_video_present(driver):
            return True
        return page_source_contains_any(driver, COURSE_READY_MARKERS)
    except Exception:
        return False


def find_visible_dialogs(driver):
    return visible_elements(
        driver,
        "//*[@role='dialog' or contains(@class,'dialog') or contains(@class,'el-dialog__wrapper')]",
    )


def close_common_dialogs(driver, logger=None):
    if not find_visible_dialogs(driver):
        return False

    text_predicate = " or ".join(f"contains(.,'{text}')" for text in COMMON_DIALOG_BUTTON_TEXTS)
    xpath = f"//button[{text_predicate}] | //i[contains(@class,'iconguanbi')]"
    buttons = visible_elements(driver, xpath)
    if not buttons:
        return False

    try:
        buttons[0].click()
        _log(logger, "info", "✅ 已尝试关闭常见弹窗")
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", buttons[0])
            _log(logger, "info", "✅ 已通过脚本尝试关闭常见弹窗")
            return True
        except Exception:
            return False


def try_click_enter_study(driver, logger=None, wait_func=None):
    for text in ENTER_STUDY_TEXTS:
        buttons = visible_elements(driver, f"//*[contains(text(),'{text}')]")
        for button in buttons:
            try:
                button.click()
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", button)
                except Exception:
                    continue
            _log(logger, "info", f"✅ 已尝试点击“{text}”按钮")
            _wait(wait_func, 2)
            return True
    return False


def is_quiz_dialog_present(driver, dialog_xpath=None):
    xpath = dialog_xpath or "//div[contains(@class,'el-dialog__wrapper') and not(contains(@style,'display: none'))]"
    return bool(visible_elements(driver, xpath))


def is_captcha_present(driver):
    markers = ["captcha", "验证码", "人机验证", "滑块", "拖动"]
    try:
        current_url = (driver.current_url or "").lower()
        if "captcha" in current_url:
            return True
    except Exception:
        pass
    return page_source_contains_any(driver, markers)

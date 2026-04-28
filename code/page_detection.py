#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Shared browser page detection helpers."""

import time

from selenium.webdriver.common.by import By


COURSE_READY_MARKERS = ["继续学习", "开始学习", "学习进度", "章节", "课程目录", "视频"]
ENTER_STUDY_TEXTS = ["继续学习", "开始学习", "进入学习", "去学习"]
COMMON_DIALOG_BUTTON_TEXTS = ["同意", "确认", "关闭", "知道了"]
COURSE_LIST_MARKERS = ["课程", "章节", "chapter", "lesson", "视频"]
CAPTCHA_MARKERS = ["验证", "captcha", "人机", "滑动", "滑块", "拼图", "安全验证", "verify", "安全检测"]
QUESTION_POPUP_CLOSE_XPATHS = [
    "//div[contains(@class, 'el-dialog__close')]",
    "//button[contains(@class, 'el-dialog__headerbtn')]",
    "//i[contains(@class, 'el-dialog__close')]",
    "//div[contains(@class, 'topic_title')]//i[contains(@class, 'iconfont')]",
    "//div[@class='btn_cancel' or @class='close-btn' or contains(@class, 'close')]",
    "//span[text()='关闭' or text()='取消']/parent::button",
]
SIDEBAR_LAYOUT_SELECTORS = [
    "//div[contains(@class, 'catalog') or contains(@class, '目录')]",
    "//div[contains(@class, 'sidebar')]",
    "//div[contains(@class, 'directory')]",
    "//aside",
    "//div[contains(@class, 'right') and contains(@class, 'panel')]",
]


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


def close_question_popup(driver, logger=None, wait_func=None):
    for xpath in QUESTION_POPUP_CLOSE_XPATHS:
        try:
            close_button = driver.find_element(By.XPATH, xpath)
            if not close_button or not close_button.is_displayed():
                continue
            _log(logger, "info", "✅ 检测到题目弹窗，正在关闭...")
            close_button.click()
            _wait(wait_func, 1)
            _log(logger, "info", "✅ 题目弹窗已关闭")
            return True
        except Exception as e:
            _log(logger, "debug", f"尝试关闭按钮失败 ({xpath}): {e}")
            continue
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
    try:
        current_url = (driver.current_url or "").lower()
        if "captcha" in current_url:
            return True
    except Exception:
        pass
    try:
        page_source = (driver.page_source or "").lower()
        return any(marker.lower() in page_source for marker in CAPTCHA_MARKERS)
    except Exception:
        return False


def detect_course_layout(driver, logger=None):
    _log(logger, "info", "正在检测课程布局类型...")
    for selector in SIDEBAR_LAYOUT_SELECTORS:
        try:
            sidebar = driver.find_element(By.XPATH, selector)
            if not sidebar or not sidebar.is_displayed():
                continue
            location = sidebar.location
            window_width = driver.execute_script("return window.innerWidth;")
            if location.get("x", 0) > window_width * 0.5:
                _log(logger, "info", "✅ 检测到新版布局（右侧目录侧边栏）")
                return "sidebar"
        except Exception as e:
            _log(logger, "debug", f"检测侧边栏失败: {e}")
            continue
    _log(logger, "info", "✅ 检测到旧版布局（主区域课程列表）")
    return "main"


def is_course_list_page(driver):
    return page_source_contains_any(driver, COURSE_LIST_MARKERS)


def wait_for_captcha_completion(check_captcha, check_login_success, logger=None, timeout=60, sleep_func=time.sleep):
    _log(logger, "info", "检测到人机验证，请手动完成验证...")
    _log(logger, "info", "⏳ 等待20秒，期间每2秒检查一次验证状态...")
    for _ in range(10):
        sleep_func(2)
        if check_login_success():
            _log(logger, "info", "✅ 登录成功，立即继续执行")
            return True
        if not check_captcha():
            _log(logger, "info", "✅ 人机验证已消失，立即继续执行")
            return True

    _log(logger, "info", "⏰ 20秒已过，开始正常检查流程...")
    start_time = time.time()
    check_interval = 5

    while time.time() - start_time < timeout:
        if not check_captcha():
            _log(logger, "info", "人机验证已完成，继续执行程序")
            return True
        if check_login_success():
            _log(logger, "info", "登录成功，继续执行程序")
            return True

        elapsed = int(time.time() - start_time)
        remaining = int(timeout - elapsed)
        _log(logger, "info", f"等待人机验证完成... 已等待 {elapsed} 秒，剩余 {remaining} 秒")
        sleep_func(check_interval)

    _log(logger, "error", "人机验证等待超时")
    return False


def wait_for_course_page_ready(driver, logger=None, wait_func=None, timeout_seconds=600, sleep_func=time.sleep):
    _log(logger, "info", "🔔 如有弹窗或未知提示，请手动处理；程序将等待进入课程页面...")
    waited = 0
    while waited < timeout_seconds:
        try:
            if is_course_page_ready(driver):
                _log(logger, "info", "✅ 已进入课程页面")
                return True
            close_common_dialogs(driver, logger=logger)
            try_click_enter_study(driver, logger=logger, wait_func=wait_func)
        except Exception:
            pass
        sleep_func(2)
        waited += 2
    _log(logger, "error", "❌ 等待进入课程页面超时，请检查课程URL是否正确或手动进入学习页")
    return False

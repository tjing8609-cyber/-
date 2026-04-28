#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Scoped actions for in-video quiz popups."""

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By


VISIBLE_DIALOG_XPATH = "//div[contains(@class,'el-dialog__wrapper') and not(contains(@style,'display: none'))]"
SUBMIT_TEXTS = ["提交", "确定", "确认", "完成", "继续"]
BLOCKED_TEXTS = ["交卷", "提交作业", "提交试卷", "提交测试", "提交考试", "确认提交", "考试提交", "作业提交"]


def _log(logger, level, message):
    if logger is None:
        return
    getattr(logger, level)(message)


def _visible(elements):
    result = []
    for element in elements:
        try:
            if element.is_displayed():
                result.append(element)
        except Exception:
            continue
    return result


def visible_quiz_dialogs(driver, dialog_xpath=None):
    xpath = dialog_xpath or VISIBLE_DIALOG_XPATH
    try:
        return _visible(driver.find_elements(By.XPATH, xpath))
    except Exception:
        return []


def _button_text(element):
    try:
        return (element.text or "").strip()
    except Exception:
        return ""


def _is_blocked(text):
    return any(marker in text for marker in BLOCKED_TEXTS)


def _click_element(driver, element):
    try:
        ActionChains(driver).move_to_element(element).pause(0.2).click().perform()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False


def find_dialog_action_buttons(dialog):
    selectors = [
        ".//button",
        ".//*[contains(@class,'dialog-footer')]//*[self::button or self::div or self::span]",
        ".//*[contains(@class,'footer')]//*[self::button or self::div or self::span]",
        ".//*[contains(@class,'btn') or contains(@class,'button')]",
    ]
    buttons = []
    for selector in selectors:
        try:
            buttons.extend(dialog.find_elements(By.XPATH, selector))
        except Exception:
            continue
    return list(dict.fromkeys(_visible(buttons)))


def click_quiz_popup_submit(driver, logger=None, dialog_xpath=None):
    """Click a submit/confirm style button inside the visible quiz popup only."""
    dialogs = visible_quiz_dialogs(driver, dialog_xpath)
    for dialog in dialogs:
        buttons = find_dialog_action_buttons(dialog)
        scored_like = []
        candidates = []
        for button in buttons:
            text = _button_text(button)
            if not text:
                continue
            if _is_blocked(text):
                scored_like.append(text)
                continue
            if any(label in text for label in SUBMIT_TEXTS):
                candidates.append((button, text))

        if scored_like:
            _log(logger, "warning", f"⚠️ 弹窗内发现正式提交类按钮，已跳过: {', '.join(scored_like)}")

        for button, text in candidates:
            if _click_element(driver, button):
                _log(logger, "info", f"✅ 已点击题目弹窗按钮: {text}")
                return True

    _log(logger, "debug", "未找到可自动点击的题目弹窗提交/确认按钮")
    return False

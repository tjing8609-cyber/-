#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Scoped actions for in-video quiz popups."""

import random
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By


VISIBLE_DIALOG_XPATH = "//div[contains(@class,'el-dialog__wrapper') and not(contains(@style,'display: none'))]"
FALLBACK_DIALOG_XPATHS = [
    VISIBLE_DIALOG_XPATH,
    "//*[@role='dialog' or contains(@class,'dialog') or contains(@class,'modal') or contains(@class,'popup') or contains(@class,'pop')]",
    "//*[contains(normalize-space(.),'AI随堂练习')]",
    "//*[contains(normalize-space(.),'提交作答')]",
    "//*[contains(normalize-space(.),'单选题') or contains(normalize-space(.),'多选题')]",
]
SUBMIT_TEXTS = ["提交", "确定", "确认", "完成", "继续"]
BLOCKED_TEXTS = ["交卷", "提交作业", "提交试卷", "提交测试", "提交考试", "确认提交", "考试提交", "作业提交"]
QUIZ_DIALOG_MARKERS = ["AI随堂练习", "提交作答", "单选题", "多选题", "判断题"]


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


def _text(element):
    try:
        return (element.text or "").strip()
    except Exception:
        return ""


def _is_probable_quiz_dialog(element):
    text = _text(element)
    if not text:
        return False
    has_question_type = any(marker in text for marker in ["单选题", "多选题", "判断题"])
    has_option_labels = ("A" in text and "B" in text) or ("A " in text and "B " in text)
    if "AI随堂练习" in text:
        return "提交作答" in text or has_question_type or has_option_labels
    if "提交作答" in text:
        return has_question_type or has_option_labels
    if has_question_type:
        return has_option_labels
    return False


def _dedupe_elements(elements):
    result = []
    seen = set()
    for element in elements:
        key = id(element)
        if key in seen:
            continue
        seen.add(key)
        result.append(element)
    return result


def visible_quiz_dialogs(driver, dialog_xpath=None):
    xpaths = [dialog_xpath] if dialog_xpath else []
    xpaths.extend(xpath for xpath in FALLBACK_DIALOG_XPATHS if xpath and xpath not in xpaths)

    candidates = []
    for xpath in xpaths:
        try:
            candidates.extend(_visible(driver.find_elements(By.XPATH, xpath)))
        except Exception:
            continue

    candidates = _dedupe_elements(candidates)
    probable = [element for element in candidates if _is_probable_quiz_dialog(element)]
    probable.sort(key=lambda element: len(_text(element)))
    return probable or candidates[:1]


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


def visible_quiz_options(driver, option_xpaths):
    options = []
    for xpath in option_xpaths or []:
        try:
            options.extend(_visible(driver.find_elements(By.XPATH, xpath)))
        except Exception:
            continue
    return list(dict.fromkeys(options))


def is_multi_choice_dialog(driver):
    try:
        elems = driver.find_elements(By.XPATH, "//span[contains(@class,'title-tit')]")
        for elem in elems:
            if elem.is_displayed() and "多选题" in ((elem.text or "").strip()):
                return True
        checkboxes = driver.find_elements(By.XPATH, "//label[contains(@class,'el-checkbox')]")
        return bool(_visible(checkboxes))
    except Exception:
        return False


def scroll_quiz_dialog(driver, position="bottom", wait_func=None):
    wrappers = visible_quiz_dialogs(driver)

    moved = False
    for wrapper in wrappers:
        try:
            try:
                view = wrapper.find_element(By.XPATH, ".//div[contains(@class,'el-scrollbar__wrap')]")
            except Exception:
                view = wrapper
            if position == "top":
                driver.execute_script("arguments[0].scrollTop = 0;", view)
            elif position == "center":
                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight/2;", view)
            else:
                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", view)
            if wait_func:
                wait_func(0.4)
            moved = True
        except Exception:
            continue
    return moved


def click_option_element(driver, option, logger=None, wait_func=None, delay=0.5):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", option)
    except Exception:
        pass
    if wait_func and delay:
        wait_func(delay)

    if _click_element(driver, option):
        return True

    _log(logger, "debug", "选项点击失败")
    return False


def select_options_by_letters(
    driver,
    options,
    letters,
    logger=None,
    wait_func=None,
    shuffle=False,
    confirm_last=False,
    after_click=None,
):
    if isinstance(letters, str):
        letters = [letters]
    allowed = [chr(ord("A") + index) for index in range(len(options or []))]
    to_click = [str(letter).strip().upper() for letter in (letters or []) if str(letter).strip().upper() in allowed]
    if shuffle:
        random.shuffle(to_click)

    clicked = 0
    last_clicked = None
    for letter in to_click:
        index = ord(letter) - ord("A")
        option = options[index]
        if click_option_element(
            driver,
            option,
            logger=logger,
            wait_func=wait_func,
            delay=random.uniform(0.5, 1.5) if wait_func else 0,
        ):
            clicked += 1
            last_clicked = option
            if after_click:
                after_click()

    if confirm_last and last_clicked is not None:
        click_option_element(
            driver,
            last_clicked,
            logger=logger,
            wait_func=wait_func,
            delay=random.uniform(0.5, 1.0) if wait_func else 0,
        )
    return clicked > 0


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

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Scoped actions for in-video quiz popups."""

import random
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By


VISIBLE_DIALOG_XPATH = "//div[contains(@class,'el-dialog__wrapper') and not(contains(@style,'display: none'))]"
VISIBLE_BLOCKING_DIALOG_XPATHS = [
    VISIBLE_DIALOG_XPATH,
    "//*[@role='dialog']",
    "//*[contains(@class,'ai-class-exercise-dialog')]",
    "//*[contains(@class,'el-overlay-dialog') or contains(@class,'modal') or contains(@class,'popup')]",
]
FALLBACK_DIALOG_XPATHS = [
    VISIBLE_DIALOG_XPATH,
    "//*[@role='dialog' or contains(@class,'dialog') or contains(@class,'modal') or contains(@class,'popup') or contains(@class,'pop')]",
    "//*[contains(@class,'ai-class-exercise-dialog')]",
    "//*[contains(@class,'ques-list')]/ancestor::*[@role='dialog' or contains(@class,'el-dialog')][1]",
    "//*[contains(@class,'question-info')]/ancestor::*[@role='dialog' or contains(@class,'el-dialog')][1]",
    "//*[contains(normalize-space(.),'AI随堂练习')]",
    "//*[contains(normalize-space(.),'提交作答')]",
    "//*[contains(normalize-space(.),'单选题') or contains(normalize-space(.),'多选题')]",
]
SUBMIT_TEXTS = ["提交", "确定", "确认", "完成", "继续"]
SUBMITTED_TEXTS = ["已提交"]
BLOCKED_TEXTS = ["交卷", "提交作业", "提交试卷", "提交测试", "提交考试", "确认提交", "考试提交", "作业提交"]
QUIZ_DIALOG_MARKERS = ["AI随堂练习", "提交作答", "单选题", "多选题", "判断题"]
CLOSE_TEXTS = ["关闭", "取消", "知道了", "我知道了", "确定", "确认", "同意", "×"]
CLOSE_BUTTON_XPATHS = [
    ".//button[contains(@class,'el-dialog__headerbtn')]",
    ".//*[contains(@class,'el-dialog__close') or contains(@class,'el-icon-close') or contains(@class,'icon-close')]",
    ".//*[@aria-label='Close' or @aria-label='close']",
    ".//img[@alt='close' or @alt='Close']",
    ".//*[contains(@class,'header-icon')]",
    ".//*[contains(@class,'close') or contains(@class,'guanbi') or contains(@class,'iconguanbi')]",
    ".//button[contains(normalize-space(.),'关闭') or contains(normalize-space(.),'取消') or contains(normalize-space(.),'知道了') or contains(normalize-space(.),'确定') or contains(normalize-space(.),'确认') or contains(normalize-space(.),'同意')]",
    ".//*[normalize-space(.)='×']",
]


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


def _attr(element, name):
    try:
        return str(element.get_attribute(name) or "")
    except Exception:
        return ""


def _has_descendant(element, xpath):
    try:
        return bool(_visible(element.find_elements(By.XPATH, xpath)))
    except Exception:
        return False


def _is_probable_quiz_dialog(element):
    text = _text(element)
    class_name = _attr(element, "class")
    has_exercise_class = "ai-class-exercise-dialog" in class_name
    has_ques_list = _has_descendant(element, ".//*[contains(@class,'ques-list')]")
    has_question_info = _has_descendant(element, ".//*[contains(@class,'question-info')]")
    has_option_nodes = _has_descendant(element, ".//*[contains(@class,'option')]")

    if has_exercise_class or (has_ques_list and (has_question_info or has_option_nodes)):
        return True

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


def _dialog_candidates(driver, dialog_xpath=None, xpaths=None):
    search_xpaths = [dialog_xpath] if dialog_xpath else []
    source_xpaths = xpaths or FALLBACK_DIALOG_XPATHS
    search_xpaths.extend(xpath for xpath in source_xpaths if xpath and xpath not in search_xpaths)

    candidates = []
    for xpath in search_xpaths:
        try:
            candidates.extend(_visible(driver.find_elements(By.XPATH, xpath)))
        except Exception:
            continue
    return _dedupe_elements(candidates)


def visible_blocking_dialogs(driver, dialog_xpath=None):
    return _dialog_candidates(driver, dialog_xpath=dialog_xpath, xpaths=VISIBLE_BLOCKING_DIALOG_XPATHS)


def probable_quiz_dialogs(driver, dialog_xpath=None):
    candidates = _dialog_candidates(driver, dialog_xpath=dialog_xpath)
    probable = [element for element in candidates if _is_probable_quiz_dialog(element)]
    probable.sort(key=lambda element: len(_text(element)))
    return probable


def visible_quiz_dialogs(driver, dialog_xpath=None):
    candidates = _dialog_candidates(driver, dialog_xpath=dialog_xpath)
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


def _looks_like_close_button(element):
    text = _button_text(element)
    if text and any(label in text for label in CLOSE_TEXTS) and not _is_blocked(text):
        return True
    try:
        class_name = str(element.get_attribute("class") or "").lower()
    except Exception:
        class_name = ""
    try:
        alt = str(element.get_attribute("alt") or "").lower()
    except Exception:
        alt = ""
    try:
        aria = str(element.get_attribute("aria-label") or "").lower()
    except Exception:
        aria = ""
    return (
        "close" in class_name
        or "guanbi" in class_name
        or "header-icon" in class_name
        or "close" in alt
        or aria == "close"
    )


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


def is_quiz_dialog_submitted(dialog):
    text = _text(dialog)
    if any(label in text for label in SUBMITTED_TEXTS):
        return True
    try:
        buttons = find_dialog_action_buttons(dialog)
    except Exception:
        buttons = []
    return any(any(label in _button_text(button) for label in SUBMITTED_TEXTS) for button in buttons)


def is_quiz_popup_submitted(driver, dialog_xpath=None):
    return any(is_quiz_dialog_submitted(dialog) for dialog in visible_quiz_dialogs(driver, dialog_xpath))


def click_quiz_popup_close(driver, logger=None, dialog_xpath=None, require_submitted=False):
    """Close a visible in-video quiz popup, optionally only after it shows submitted state."""
    dialogs = visible_quiz_dialogs(driver, dialog_xpath)
    for dialog in dialogs:
        if require_submitted and not is_quiz_dialog_submitted(dialog):
            continue

        buttons = []
        for selector in CLOSE_BUTTON_XPATHS:
            try:
                buttons.extend(dialog.find_elements(By.XPATH, selector))
            except Exception:
                continue

        for button in _visible(_dedupe_elements(buttons)):
            if not _looks_like_close_button(button):
                continue
            if _click_element(driver, button):
                _log(logger, "info", "已点击题目弹窗关闭按钮")
                return True

    return False


def click_first_non_quiz_dialog_close(driver, logger=None, dialog_xpath=None):
    """Close one visible non-quiz modal/dialog and leave quiz dialogs for the agent."""
    dialogs = visible_blocking_dialogs(driver, dialog_xpath=dialog_xpath)
    for dialog in dialogs:
        if _is_probable_quiz_dialog(dialog):
            continue

        buttons = []
        for selector in CLOSE_BUTTON_XPATHS:
            try:
                buttons.extend(dialog.find_elements(By.XPATH, selector))
            except Exception:
                continue

        for button in _visible(_dedupe_elements(buttons)):
            if not _looks_like_close_button(button):
                continue
            if _click_element(driver, button):
                _log(logger, "info", "✅ 已关闭一个非题目弹窗")
                return True

    return False


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
        elems = driver.find_elements(
            By.XPATH,
            "//*[contains(@class,'title-tit') or contains(@class,'type') or contains(@class,'ai-class-exercise-dialog')]",
        )
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
            if any(label in text for label in SUBMITTED_TEXTS):
                _log(logger, "info", f"题目弹窗已处于提交完成状态: {text}")
                return True
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

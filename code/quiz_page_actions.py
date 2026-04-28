import random

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By


CLICKABLE_OPTION_SELECTORS = [
    ".//span[contains(@class, 'el-radio__inner')]",
    ".//span[contains(@class, 'el-checkbox__inner')]",
    ".//input[@type='radio']",
    ".//input[@type='checkbox']",
    ".//label",
]
GRAY_NEXT_SELECTORS = [
    "//span[contains(@class, 'Topicswitchingbtn-gray')]",
    "//span[contains(@class, 'Topicswitchingbtn') and contains(@class, 'gray')]",
    "//button[contains(@class, 'next') and (@disabled or contains(@class, 'disabled'))]",
]
NEXT_BUTTON_SELECTORS = [
    "//span[contains(@class, 'Topicswitchingbtn') and contains(text(), '下一题')]",
    "//div[contains(@class, 'Topicswitchingbtn') and contains(text(), '下一题')]",
    "//button[contains(text(), '下一题')]",
    "//span[contains(text(), '下一题')]",
    "//div[contains(text(), '下一题')]",
    "//a[contains(text(), '下一题')]",
    "//button[contains(@class, 'next')]",
]


def _log(logger, level, message):
    if logger is None:
        return
    getattr(logger, level)(message)


def _wait(wait_func, seconds):
    if wait_func is None:
        return
    wait_func(seconds)


def find_clickable_option_element(parent_elem, logger=None):
    for selector in CLICKABLE_OPTION_SELECTORS:
        try:
            element = parent_elem.find_element(By.XPATH, selector)
            if element:
                _log(logger, "debug", f"找到可点击元素: {selector}")
                return element
        except Exception:
            continue
    _log(logger, "debug", "使用父元素作为点击目标")
    return parent_elem


def action_click(driver, element, min_pause=0.3, max_pause=0.8):
    actions = ActionChains(driver)
    actions.move_to_element(element)
    actions.pause(random.uniform(min_pause, max_pause))
    actions.click()
    actions.perform()


def select_answer_options(driver, answer, question_data, logger=None, wait_func=None):
    options = question_data["options"]
    question_type = question_data["type"]
    if isinstance(answer, str):
        answer = [answer]

    _log(logger, "info", f"👆 选择答案: {', '.join(answer)}")
    for letter in answer:
        if letter not in options:
            _log(logger, "warning", f"⚠️  答案 {letter} 不在选项中")
            continue

        option_element = options[letter]["element"]
        clickable_element = find_clickable_option_element(option_element, logger=logger)
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", clickable_element)
        _wait(wait_func, 0.5)
        action_click(driver, clickable_element)
        _log(logger, "info", f"✅ 已点击选项: {letter}")

        if question_type == "multiple" and len(answer) > 1:
            _wait(wait_func, random.uniform(0.5, 1.0))

    _wait(wait_func, random.uniform(1, 2))
    return True


def is_next_button_disabled(driver, logger=None):
    for selector in GRAY_NEXT_SELECTORS:
        try:
            gray_buttons = driver.find_elements(By.XPATH, selector)
            for button in gray_buttons:
                if "下一题" in button.text:
                    _log(logger, "info", "🏁 检测到下一题按钮变灰，已是最后一题")
                    return True
        except Exception:
            continue
    return False


def find_next_button(driver):
    for selector in NEXT_BUTTON_SELECTORS:
        try:
            elements = driver.find_elements(By.XPATH, selector)
            for element in elements:
                element_class = element.get_attribute("class") or ""
                if "gray" in element_class.lower() or "disabled" in element_class.lower():
                    continue
                if "下一题" in element.text or "next" in element_class.lower():
                    return element
        except Exception:
            continue
    return None


def click_next_button(driver, logger=None, wait_func=None):
    if is_next_button_disabled(driver, logger=logger):
        return False

    next_button = find_next_button(driver)
    if not next_button:
        _log(logger, "info", "ℹ️  未找到可点击的下一题按钮")
        return False

    action_click(driver, next_button, min_pause=0.5, max_pause=1.0)
    _log(logger, "info", "✅ 已点击下一题")
    _wait(wait_func, 2)
    return True


__all__ = [
    "click_next_button",
    "find_clickable_option_element",
    "find_next_button",
    "is_next_button_disabled",
    "select_answer_options",
]

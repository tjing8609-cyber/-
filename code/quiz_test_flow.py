import random
import re
from dataclasses import dataclass

from selenium.webdriver.common.by import By

from element_actions import click_element


QUIZ_STATUS_SELECTORS = [
    "//span[contains(text(), '已批阅')]",
    "//span[contains(text(), '已提交')]",
    "//span[contains(text(), '已完成')]",
    "//span[contains(text(), '查看作业')]",
    "//button[contains(text(), '查看作业')]",
]
GRAY_NEXT_SELECTORS = [
    "//span[contains(@class, 'Topicswitchingbtn-gray')]",
    "//span[contains(@class, 'Topicswitchingbtn') and contains(@class, 'gray')]",
]
ANSWER_CARD_CONTAINER_SELECTORS = [
    "//div[contains(@class, 'el-scrollbar__view')]",
    "//div[@class='el-dialog__body']",
]
ANSWER_CARD_ITEM_SELECTORS = [
    "//li[contains(@class, 'questionlistall') or contains(@class, 'green')]",
    "//div[@class='el-dialog__body']//li",
]
START_BUTTON_SELECTORS = [
    ".//button[contains(text(), '开始做题')]",
    ".//div[contains(text(), '开始做题')]",
    ".//a[contains(text(), '开始做题')]",
    ".//span[contains(text(), '开始做题')]",
    ".//div[contains(@class, 'btn') and contains(@class, 'start')]",
    ".//div[contains(@class, 'btn') and contains(@class, 'do')]",
    ".//button[contains(@class, 'start')]",
    ".//button[contains(text(), '开始')]",
    ".//div[contains(text(), '开始')]",
    ".//span[contains(text(), '开始')]",
    ".//a[contains(text(), '开始')]",
]
GLOBAL_START_BUTTON_SELECTORS = [
    "//button[contains(text(), '开始做题')]",
    "//div[contains(text(), '开始做题')]",
    "//a[contains(text(), '开始做题')]",
]
COMPLETED_KEYWORDS = ["已完成", "已提交", "已做", "100%", "满分"]
SUBMIT_SELECTORS = [
    "//span[contains(@class, 'Submithomeworkbtn')]",
    "//div[contains(@class, 'Submithomeworkbtn')]",
    "//button[contains(text(), '提交')]",
    "//span[contains(text(), '提交')]",
    "//div[contains(text(), '提交')]",
    "//button[contains(text(), '交卷')]",
    "//span[contains(text(), '交卷')]",
    "//span[contains(text(), '提交作业')]",
]
CONFIRM_SUBMIT_SELECTORS = [
    "//button[contains(@class, 'Submissionbtn') and contains(@class, 'el-button--primary')]",
    "//button[contains(@class, 'Submissionbtn')]",
    "//button[contains(@class, 'el-button--primary') and contains(text(), '提交')]",
    "//button[contains(@class, 'el-button--primary') and contains(text(), '确定')]",
    "//button[contains(@class, 'el-button--primary') and contains(text(), '确认')]",
    "//span[contains(text(), '提交')]/parent::button[contains(@class, 'el-button--primary')]",
]


@dataclass
class AnswerCardStats:
    total_count: int = 0
    answered_count: int = 0
    current_count: int = 0
    unanswered_count: int = 0
    last_question_index: int = -1
    current_question_index: int = -1

    @property
    def ready_to_submit(self):
        return (
            self.current_count == 1
            and self.current_question_index == self.last_question_index
            and self.answered_count == self.total_count - 1
            and self.unanswered_count == 0
        )


def _log(logger, level, message):
    if logger is None:
        return
    getattr(logger, level)(message)


def _wait(wait_func, seconds):
    if wait_func is None:
        return
    wait_func(seconds)


def first_quiz_status(driver):
    for selector in QUIZ_STATUS_SELECTORS:
        try:
            elements = driver.find_elements(By.XPATH, selector)
            if elements:
                return elements[0].text.strip()
        except Exception:
            continue
    return None


def log_quiz_status_change(driver, logger=None):
    _log(logger, "info", "🔍 检查题目状态...")
    status_text = first_quiz_status(driver)
    if status_text:
        _log(logger, "info", f"✅ 题目状态: {status_text}")
        return status_text
    _log(logger, "info", "ℹ️  未检测到明确的状态变化")
    return None


def is_next_button_disabled(driver, logger=None):
    for selector in GRAY_NEXT_SELECTORS:
        try:
            gray_buttons = driver.find_elements(By.XPATH, selector)
            if gray_buttons:
                _log(logger, "info", "✅ 判断1: 下一题按钮变灰")
                return True
        except Exception:
            continue
    _log(logger, "info", "❌ 判断1: 下一题按钮未变灰")
    return False


def find_answer_card_container(driver):
    for selector in ANSWER_CARD_CONTAINER_SELECTORS:
        try:
            containers = driver.find_elements(By.XPATH, selector)
            if containers:
                return containers[0]
        except Exception:
            continue
    return None


def find_answer_card_items(driver):
    for selector in ANSWER_CARD_ITEM_SELECTORS:
        try:
            question_items = driver.find_elements(By.XPATH, selector)
            if question_items:
                return question_items
        except Exception:
            continue
    return []


def _is_answered_item(item_class, bg_color):
    if "greenbgcur" in item_class:
        return True
    if not bg_color:
        return False
    rgb_match = re.search(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", bg_color)
    if not rgb_match:
        return False
    r, g, b = map(int, rgb_match.groups())
    hex_color = f"#{r:02x}{g:02x}{b:02x}".upper()
    return hex_color == "#D1F8EE" or (r > 200 and g > 240 and b > 230)


def read_answer_card_stats(driver, logger=None, wait_func=None):
    _log(logger, "info", "📋 检查右侧答题卡...")
    answer_card_container = find_answer_card_container(driver)
    if answer_card_container:
        _log(logger, "info", "📜 滚动答题卡到底部...")
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", answer_card_container)
        _wait(wait_func, 1)

    stats = AnswerCardStats()
    for index, item in enumerate(find_answer_card_items(driver)):
        try:
            if not item.text.strip().isdigit():
                continue
            item_class = item.get_attribute("class") or ""
            bg_color = item.value_of_css_property("background-color")
            is_answered = _is_answered_item(item_class, bg_color)
            is_current = "greenbordercur" in item_class

            stats.total_count += 1
            stats.last_question_index = index
            if is_current:
                stats.current_count += 1
                stats.current_question_index = index
                _log(logger, "debug", f"题号 {item.text}: 正在答题")
            elif is_answered:
                stats.answered_count += 1
                _log(logger, "debug", f"题号 {item.text}: 已答题")
            else:
                stats.unanswered_count += 1
                _log(logger, "debug", f"题号 {item.text}: 未答题 (bg={bg_color})")
        except Exception:
            continue
    return stats


def is_answer_card_ready_for_submit(driver, logger=None, wait_func=None):
    stats = read_answer_card_stats(driver, logger=logger, wait_func=wait_func)
    _log(
        logger,
        "info",
        f"📊 统计: 总题数={stats.total_count}, 已答={stats.answered_count}, 正在答={stats.current_count}, 未答={stats.unanswered_count}",
    )
    if stats.ready_to_submit:
        _log(logger, "info", "✅ 判断2: 答题卡检查通过！除了最后一题正在答，其余均已答")
        return True
    _log(
        logger,
        "warning",
        f"⚠️  判断2: 答题卡状态不符合（正在答={stats.current_count}, 当前题是最后一题={stats.current_question_index == stats.last_question_index}, 未答={stats.unanswered_count}）",
    )
    return False


def is_last_question(driver, logger=None, wait_func=None):
    if not is_next_button_disabled(driver, logger=logger):
        return False
    if is_answer_card_ready_for_submit(driver, logger=logger, wait_func=wait_func):
        _log(logger, "info", "✅ 双重确认: 这是最后一题！")
        return True
    return False


def find_start_button(driver, container, logger=None):
    for selector in START_BUTTON_SELECTORS:
        try:
            buttons = container.find_elements(By.XPATH, selector)
            for button in buttons:
                button_text = button.text.strip()
                button_class = button.get_attribute("class") or ""
                if "开始做题" in button_text:
                    _log(logger, "info", f"✅ 找到'开始做题'按钮: {button_text}")
                    return button
                if "开始" in button_text and ("测试" in button_text or "考试" in button_text):
                    _log(logger, "info", f"✅ 找到开始按钮: {button_text}")
                    return button
                if "do" in button_class.lower() or "start" in button_class.lower():
                    if button.is_displayed() and button.is_enabled():
                        _log(logger, "info", f"✅ 找到按钮class: {button_class[:50]}")
                        return button
        except Exception:
            continue

    _log(logger, "warning", "⚠️  未找到'开始做题'按钮，尝试在全页面查找...")
    for selector in GLOBAL_START_BUTTON_SELECTORS:
        try:
            buttons = driver.find_elements(By.XPATH, selector)
            for button in buttons:
                if "开始做题" in button.text and button.is_displayed():
                    _log(logger, "info", f"✅ 全页面找到'开始做题'按钮: {button.text}")
                    return button
        except Exception:
            continue

    _log(logger, "error", "❌ 未找到'开始做题'按钮")
    return None


def is_quiz_completed(quiz_element, progress=None, logger=None):
    if not quiz_element:
        return False
    element_text = quiz_element.text
    for keyword in COMPLETED_KEYWORDS:
        if keyword in element_text:
            _log(logger, "info", f"检测到测试已完成: {element_text[:30]}")
            return True

    progress = progress or {}
    quiz_id = quiz_element.get_attribute("id") or element_text[:20]
    if quiz_id in progress.get("completed_quizzes", []):
        _log(logger, "info", f"进度记录显示该测试已完成: {quiz_id}")
        return True
    return False


def find_submit_button(driver):
    for selector in SUBMIT_SELECTORS:
        try:
            elements = driver.find_elements(By.XPATH, selector)
            for element in elements:
                if "提交" in element.text or "交卷" in element.text:
                    return element
        except Exception:
            continue
    return None


def find_submit_confirm_button(driver):
    for selector in CONFIRM_SUBMIT_SELECTORS:
        try:
            elements = driver.find_elements(By.XPATH, selector)
            for element in elements:
                if element.is_displayed():
                    return element
        except Exception:
            continue
    return None


def confirm_submit(driver, logger=None, wait_func=None):
    _log(logger, "info", "🔍 查找确认弹窗...")
    _wait(wait_func, 2)
    confirm_button = find_submit_confirm_button(driver)
    if not confirm_button:
        _log(logger, "warning", "⚠️  未找到确认按钮")
        return False
    if click_element(driver, confirm_button, logger=logger, wait_func=wait_func, wait_seconds=3, scroll=False):
        _log(logger, "info", "✅ 已确认提交")
        return True
    return False


def submit_quiz(driver, logger=None, wait_func=None):
    submit_button = find_submit_button(driver)
    if not submit_button:
        return False
    _log(logger, "info", "📝 找到提交按钮")
    _wait(wait_func, random.uniform(2, 4))
    if not click_element(driver, submit_button, logger=logger, wait_func=wait_func, wait_seconds=3, scroll=False):
        return False
    _log(logger, "info", "✅ 已点击提交")
    confirm_submit(driver, logger=logger, wait_func=wait_func)
    return True


__all__ = [
    "AnswerCardStats",
    "confirm_submit",
    "find_start_button",
    "first_quiz_status",
    "is_answer_card_ready_for_submit",
    "is_last_question",
    "is_quiz_completed",
    "log_quiz_status_change",
    "read_answer_card_stats",
    "submit_quiz",
]

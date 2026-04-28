import random
from dataclasses import dataclass

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


EXAM_TAB_SELECTORS = [
    "//div[contains(text(), '作业考试')]",
    "//span[contains(text(), '作业考试')]",
    "//a[contains(text(), '作业考试')]",
    "//div[contains(text(), '考试')]",
]
QUIZ_LIST_CONTAINER_SELECTORS = [
    "//div[contains(@class, 'homework-list')]",
    "//div[contains(@class, 'exam-list')]",
    "//div[contains(@class, 'test-list')]",
    "//div[contains(@class, 'list-container')]",
    "//div[contains(@class, 'content')]",
]
QUIZ_ENTRY_BASE_SELECTORS = [
    "//div[contains(@class, 'homework-item')]",
    "//div[contains(@class, 'exam-item')]",
    "//div[contains(@class, 'test-item')]",
    "//div[contains(text(), '测试')]",
    "//span[contains(text(), '测试')]",
    "//a[contains(text(), '测试')]",
]
SKIP_QUIZ_KEYWORDS = ["已完成", "已提交", "已批阅", "查看作业", "查看", "已做", "100%", "满分"]
QUIZ_PAGE_SELECTORS = [
    "//div[contains(@class, 'topic')]",
    "//div[contains(@class, 'question')]",
    "//div[contains(@class, 'exam')]",
    "//div[contains(@class, 'test')]",
    "//li[contains(@class, 'topic-item')]",
]


@dataclass
class QuizEntrance:
    container: object = None
    start_button: object = None

    @property
    def found(self):
        return self.container is not None and self.start_button is not None


def _log(logger, level, message):
    if logger is None:
        return
    getattr(logger, level)(message)


def _wait(wait_func, seconds):
    if wait_func is None:
        return
    wait_func(seconds)


def switch_to_exam_tab(driver, logger=None, wait_func=None):
    for selector in EXAM_TAB_SELECTORS:
        try:
            tabs = driver.find_elements(By.XPATH, selector)
            for tab in tabs:
                if "作业" in tab.text or "考试" in tab.text:
                    _log(logger, "info", f"切换到tab: {tab.text}")
                    tab.click()
                    _wait(wait_func, 2)
                    return True
        except Exception:
            continue
    _log(logger, "info", "未找到作业考试tab，可能已在该页面")
    return True


def scroll_to_load_all_quizzes(driver, logger=None, wait_func=None):
    _log(logger, "info", "📜 滚动页面加载所有测试...")
    scroll_container = None
    for selector in QUIZ_LIST_CONTAINER_SELECTORS:
        try:
            elements = driver.find_elements(By.XPATH, selector)
            if elements:
                scroll_container = elements[0]
                _log(logger, "info", f"✅ 找到滚动容器: {selector}")
                break
        except Exception:
            continue

    if scroll_container:
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scroll_container)
        _wait(wait_func, 1)
        driver.execute_script("arguments[0].scrollTop = 0", scroll_container)
        _log(logger, "info", "✅ 已滚动容器")
    else:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        _wait(wait_func, 1)
        driver.execute_script("window.scrollTo(0, 0);")
        _log(logger, "info", "✅ 已滚动页面")
    _wait(wait_func, 2)


def quiz_entry_selectors(quiz_type):
    return [
        *QUIZ_ENTRY_BASE_SELECTORS[:3],
        f"//div[contains(text(), '{quiz_type}')]",
        f"//span[contains(text(), '{quiz_type}')]",
        f"//a[contains(text(), '{quiz_type}')]",
        f"//button[contains(text(), '{quiz_type}')]",
        f"//li[contains(text(), '{quiz_type}')]",
        *QUIZ_ENTRY_BASE_SELECTORS[3:],
    ]


def is_completed_quiz_text(text):
    return any(keyword in text for keyword in SKIP_QUIZ_KEYWORDS)


def find_quiz_entrance(driver, quiz_type, find_start_button, logger=None, wait_func=None):
    _log(logger, "info", f"正在查找测试入口: {quiz_type}")
    switch_to_exam_tab(driver, logger=logger, wait_func=wait_func)
    scroll_to_load_all_quizzes(driver, logger=logger, wait_func=wait_func)

    for selector in quiz_entry_selectors(quiz_type):
        try:
            elements = driver.find_elements(By.XPATH, selector)
            for element in elements:
                element_text = element.text
                if quiz_type not in element_text and "测试" not in element_text and "作业" not in element_text:
                    continue
                if is_completed_quiz_text(element_text):
                    _log(logger, "info", f"⏭️  跳过已完成测试: {element_text[:50]}...")
                    continue
                _log(logger, "info", f"找到未完成测试: {element_text[:50]}...")
                start_button = find_start_button(element)
                if start_button:
                    return QuizEntrance(container=element, start_button=start_button)
        except Exception:
            continue
    return QuizEntrance()


def click_element_with_action(driver, element, min_pause=0.5, max_pause=1.5):
    actions = ActionChains(driver)
    actions.move_to_element(element)
    actions.pause(random.uniform(min_pause, max_pause))
    actions.click()
    actions.perform()


def handle_window_switch(driver, logger=None, wait_func=None):
    try:
        current_windows = driver.window_handles
        if len(current_windows) > 1:
            _log(logger, "info", "检测到新窗口，切换到新窗口")
            driver.switch_to.window(current_windows[-1])
            _wait(wait_func, 2)

        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            if iframes:
                _log(logger, "info", f"检测到 {len(iframes)} 个iframe")
                for iframe in iframes:
                    try:
                        driver.switch_to.frame(iframe)
                        _log(logger, "info", "已切换到iframe")
                        _wait(wait_func, 1)
                        break
                    except Exception:
                        driver.switch_to.default_content()
                        continue
        except Exception as e:
            _log(logger, "debug", f"iframe检查: {e}")
    except Exception as e:
        _log(logger, "error", f"窗口切换处理失败: {e}")


def wait_for_quiz_page(driver, logger=None):
    _log(logger, "info", "等待答题页面加载...")
    for selector in QUIZ_PAGE_SELECTORS:
        try:
            element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, selector))
            )
            if element:
                _log(logger, "info", f"✅ 答题页面加载成功，检测到元素: {selector}")
                return True
        except TimeoutException:
            continue

    current_url = driver.current_url
    if "exam" in current_url or "test" in current_url or "quiz" in current_url:
        _log(logger, "info", f"✅ 根据URL判断已进入答题页面: {current_url}")
        return True
    _log(logger, "warning", "⚠️  未检测到标准答题页面元素")
    return False


def enter_quiz_page(driver, quiz_element, logger=None, wait_func=None):
    if not quiz_element:
        _log(logger, "error", "测试元素不存在")
        return False

    _log(logger, "info", "正在进入测试...")
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", quiz_element)
    _wait(wait_func, 1)
    click_element_with_action(driver, quiz_element)
    _log(logger, "info", "已点击测试入口")
    _wait(wait_func, 3)
    handle_window_switch(driver, logger=logger, wait_func=wait_func)
    if wait_for_quiz_page(driver, logger=logger):
        return True
    _log(logger, "error", "答题页面加载超时")
    return False


__all__ = [
    "QuizEntrance",
    "enter_quiz_page",
    "find_quiz_entrance",
    "handle_window_switch",
    "is_completed_quiz_text",
    "quiz_entry_selectors",
    "scroll_to_load_all_quizzes",
    "switch_to_exam_tab",
    "wait_for_quiz_page",
]

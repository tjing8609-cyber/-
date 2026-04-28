from selenium.webdriver.common.by import By


ENTRY_DIALOG_XPATHS = [
    "//button[contains(@class,'agree-btn')]",
    "//button[contains(@class,'btn') and (contains(.,'同意') or contains(.,'确认') or contains(.,'知道了') or contains(.,'我知道了'))]",
    "//span[contains(.,'同意')]/ancestor::button",
    "//*[@role='dialog']//button[contains(.,'同意') or contains(.,'确认') or contains(.,'知道了')]",
    "//i[contains(@class,'iconguanbi')]",
]


def _log(logger, level, message):
    if logger is None:
        return
    getattr(logger, level)(message)


def _wait(wait_func, seconds):
    if wait_func is None:
        return
    wait_func(seconds)


def normalize_course_url(course_url):
    return str(course_url or "").strip()


def has_course_url(course_url):
    return bool(normalize_course_url(course_url))


def _visible(elements):
    visible = []
    for element in elements:
        try:
            if element.is_displayed():
                visible.append(element)
        except Exception:
            visible.append(element)
    return visible


def click_entry_dialogs(driver, logger=None, wait_func=None, max_clicks=5):
    clicked = 0
    for xpath in ENTRY_DIALOG_XPATHS:
        if clicked >= max_clicks:
            break
        try:
            elements = _visible(driver.find_elements(By.XPATH, xpath))
        except Exception:
            continue
        for element in elements:
            if clicked >= max_clicks:
                break
            try:
                element.click()
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", element)
                except Exception:
                    continue
            clicked += 1
            _log(logger, "info", "✅ 已尝试处理课程入口弹窗")
            _wait(wait_func, 1)
    return clicked


def open_course_url(driver, course_url, wait_ready_func=None, logger=None, wait_func=None):
    url = normalize_course_url(course_url)
    if not url:
        return False

    _log(logger, "info", f"🌐 检测到course_url，直接跳转: {url}")
    _log(logger, "info", "✅ 跳过课程查找步骤")
    try:
        driver.get(url)
        _wait(wait_func, 3)
        _log(logger, "info", "✅ 已成功跳转到课程URL")
        click_entry_dialogs(driver, logger=logger, wait_func=wait_func)
        if wait_ready_func is None:
            return True
        return bool(wait_ready_func())
    except Exception as e:
        _log(logger, "error", f"❌ 跳转到课程URL失败: {e}")
        _log(logger, "info", "🔔 请手动进入课程页面，程序将等待...")
        if wait_ready_func is None:
            return False
        return bool(wait_ready_func())


__all__ = [
    "click_entry_dialogs",
    "has_course_url",
    "normalize_course_url",
    "open_course_url",
]

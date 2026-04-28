from selenium.webdriver.common.action_chains import ActionChains


def _log(logger, level, message):
    if logger is None:
        return
    getattr(logger, level)(message)


def _wait(wait_func, seconds):
    if wait_func is None:
        return
    wait_func(seconds)


def scroll_into_view(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        return True
    except Exception:
        return False


def click_element(driver, element, logger=None, wait_func=None, wait_seconds=0, scroll=True):
    if scroll:
        scroll_into_view(driver, element)
        _wait(wait_func, min(wait_seconds, 1) if wait_seconds else 0)

    try:
        element.click()
        _wait(wait_func, wait_seconds)
        return True
    except Exception as click_error:
        _log(logger, "debug", f"普通点击失败: {click_error}")

    try:
        actions = ActionChains(driver)
        actions.move_to_element(element)
        actions.click()
        actions.perform()
        _wait(wait_func, wait_seconds)
        return True
    except Exception as action_error:
        _log(logger, "debug", f"ActionChains点击失败: {action_error}")

    try:
        driver.execute_script("arguments[0].click();", element)
        _wait(wait_func, wait_seconds)
        return True
    except Exception as js_error:
        _log(logger, "debug", f"JavaScript点击失败: {js_error}")
        return False


def scroll_page_to_load(driver, wait_func=None, passes=3, delay=1):
    for _ in range(max(0, passes)):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            return False
        _wait(wait_func, delay)
        try:
            driver.execute_script("window.scrollTo(0, 0);")
        except Exception:
            return False
        _wait(wait_func, delay)
    return True


def switch_to_latest_window(driver):
    try:
        if len(driver.window_handles) > 1:
            driver.switch_to.window(driver.window_handles[-1])
            return True
    except Exception:
        return False
    return False

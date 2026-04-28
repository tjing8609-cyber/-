from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from element_actions import click_element


USERNAME_SELECTORS = [
    "//input[@type='text']",
    "//input[@placeholder='手机号']",
    "//input[contains(@placeholder, '账号')]",
    "//input[contains(@placeholder, '用户')]",
    "//input[contains(@id, 'username')]",
    "//input[contains(@name, 'username')]",
    "//input[contains(@class, 'username')]",
    "//input[contains(@class, 'account')]",
]
PASSWORD_SELECTORS = [
    "//input[@type='password']",
    "//input[@placeholder='密码']",
    "//input[contains(@placeholder, '密码')]",
    "//input[contains(@id, 'password')]",
    "//input[contains(@name, 'password')]",
    "//input[contains(@class, 'password')]",
]
LOGIN_BUTTON_SELECTORS = [
    "//button[contains(text(), '登录')]",
    "//button[contains(text(), '登 录')]",
    "//a[contains(text(), '登录')]",
    "//span[contains(text(), '登录')]",
    "//div[contains(text(), '登录')]",
    "//button[contains(@class, 'login')]",
    "//button[@type='submit']",
    "//input[@type='submit']",
    "//div[contains(@class, 'login-btn')]",
    "//div[contains(@class, 'loginBtn')]",
    "//span[contains(text(), '登录')]/parent::button",
    "//span[contains(text(), '登录')]/parent::div",
    "//span[contains(text(), '登录')]/parent::a",
    "//button",
    "//div[@role='button']",
]


def _log(logger, level, message):
    if logger is None:
        return
    getattr(logger, level)(message)


def _wait(wait_func, seconds):
    if wait_func is None:
        return
    wait_func(seconds)


def find_input(wait, selectors, logger=None, label="输入框"):
    for selector in selectors:
        try:
            element = wait.until(EC.presence_of_element_located((By.XPATH, selector)))
            _log(logger, "info", f"找到{label}: {selector}")
            return element
        except Exception:
            continue
    _log(logger, "warning", f"未找到{label}")
    return None


def find_login_button(driver, logger=None):
    for selector in LOGIN_BUTTON_SELECTORS:
        try:
            elements = driver.find_elements(By.XPATH, selector)
        except Exception:
            continue
        for element in elements:
            try:
                text = element.text or ""
                if "登录" in text or "login" in text.lower():
                    _log(logger, "info", f"找到登录按钮: {selector}, 文本: {text}")
                    return element
            except Exception:
                continue
    _log(logger, "warning", "未找到登录按钮")
    return None


def login_method_standard(driver, wait, username, password, logger=None, wait_func=None):
    _log(logger, "info", "尝试标准登录方式1...")

    username_input = find_input(wait, USERNAME_SELECTORS, logger=logger, label="用户名输入框")
    if username_input is None:
        return False
    username_input.clear()
    username_input.send_keys(username)
    _log(logger, "info", f"已输入用户名: {username}")
    _wait(wait_func, 1)

    password_input = find_input(wait, PASSWORD_SELECTORS, logger=logger, label="密码输入框")
    if password_input is None:
        return False
    password_input.clear()
    password_input.send_keys(password)
    _log(logger, "info", "已输入密码")
    _wait(wait_func, 1)

    login_button = find_login_button(driver, logger=logger)
    if login_button is None:
        return False
    if not click_element(driver, login_button, logger=logger, wait_func=wait_func, wait_seconds=3, scroll=False):
        return False
    _log(logger, "info", "已点击登录按钮")
    return True


def login_method_script(driver, username, password, logger=None):
    script = """
    var username = arguments[0];
    var password = arguments[1];
    var usernameInputs = document.querySelectorAll('input[type="text"], input[placeholder*="手机"], input[id*="username"]');
    var passwordInputs = document.querySelectorAll('input[type="password"], input[placeholder*="密码"], input[id*="password"]');
    if (usernameInputs.length > 0 && passwordInputs.length > 0) {
        usernameInputs[0].value = username;
        passwordInputs[0].value = password;
        usernameInputs[0].dispatchEvent(new Event('input', { bubbles: true }));
        passwordInputs[0].dispatchEvent(new Event('input', { bubbles: true }));
        return true;
    }
    return false;
    """
    try:
        result = driver.execute_script(script, username, password)
    except Exception as e:
        _log(logger, "warning", f"脚本写入账号密码失败: {e}")
        return False

    if not result:
        return False

    try:
        login_button = driver.find_element(
            By.XPATH,
            "//button[contains(text(), '登录')] | //button[@type='submit'] | //input[@type='submit']",
        )
    except Exception as e:
        _log(logger, "error", f"脚本登录后未找到登录按钮: {e}")
        return False

    if click_element(driver, login_button, logger=logger, scroll=False):
        _log(logger, "info", "已通过脚本辅助点击登录按钮")
        return True
    return False


def try_login_methods(driver, wait, username, password, logger=None, wait_func=None):
    methods = [
        ("login_method_standard", lambda: login_method_standard(driver, wait, username, password, logger=logger, wait_func=wait_func)),
        ("login_method_script", lambda: login_method_script(driver, username, password, logger=logger)),
    ]
    for name, method in methods:
        try:
            if method():
                return True
        except Exception as e:
            _log(logger, "warning", f"登录方式 {name} 失败: {e}")
    return False


__all__ = [
    "find_input",
    "find_login_button",
    "login_method_script",
    "login_method_standard",
    "try_login_methods",
]

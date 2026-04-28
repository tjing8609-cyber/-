from dataclasses import dataclass


LOGIN_MARKERS = ("登录", "手机号", "password")
LOGGED_IN_MARKERS = ("我的课程", "课程列表")


@dataclass(frozen=True)
class LoginPageState:
    current_url: str
    page_source: str


def mask_username(username):
    text = str(username or "")
    if not text:
        return ""
    suffix = text[-2:] if len(text) > 5 else "**"
    return f"{text[:3]}****{suffix}"


def read_login_page_state(driver):
    return LoginPageState(
        current_url=driver.current_url or "",
        page_source=driver.page_source or "",
    )


def is_login_required_state(current_url="", page_source=""):
    current_url = current_url or ""
    page_source = page_source or ""
    return any([
        "login" in current_url.lower(),
        any(marker in page_source for marker in LOGIN_MARKERS),
    ])


def is_login_success_state(current_url="", page_source=""):
    current_url = current_url or ""
    page_source = page_source or ""
    if "onlinestuh5" in current_url and "login" not in current_url.lower():
        return True
    return any(marker in page_source for marker in LOGGED_IN_MARKERS)


def is_login_required(driver):
    state = read_login_page_state(driver)
    return is_login_required_state(state.current_url, state.page_source)


def is_login_success(driver):
    state = read_login_page_state(driver)
    return is_login_success_state(state.current_url, state.page_source)


__all__ = [
    "LoginPageState",
    "is_login_required",
    "is_login_required_state",
    "is_login_success",
    "is_login_success_state",
    "mask_username",
    "read_login_page_state",
]

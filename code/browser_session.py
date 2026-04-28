import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/91.0.4472.124 Safari/537.36"
)


@dataclass(frozen=True)
class BrowserSession:
    driver: object
    wait: object
    browser_name: str


def resolve_local_driver_paths(project_root, cwd=None):
    root = Path(project_root)
    current_dir = Path(cwd or os.getcwd())
    candidates = [
        root / "code" / "chromedriver.exe",
        root / "chromedriver.exe",
        root / "code" / "chromedriver-win64" / "chromedriver.exe",
        current_dir / "chromedriver.exe",
    ]

    seen = set()
    paths = []
    for candidate in candidates:
        key = str(candidate.resolve(strict=False)).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            paths.append(str(candidate))
    return paths


def _log(logger, level, message):
    if logger is None:
        return
    getattr(logger, level)(message)


def build_chrome_options(headless=False, window_size="1349,768", user_agent=DEFAULT_CHROME_USER_AGENT):
    from selenium.webdriver.chrome.options import Options

    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(f"--window-size={window_size}")
    options.add_argument(f"--user-agent={user_agent}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return options


def build_edge_options(headless=False, window_size="1349,768"):
    from selenium.webdriver.edge.options import Options as EdgeOptions

    options = EdgeOptions()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(f"--window-size={window_size}")
    return options


def hide_webdriver_flag(driver, logger=None):
    try:
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return True
    except Exception as e:
        _log(logger, "warning", f"隐藏 webdriver 标记失败: {e}")
        return False


def _create_chrome_with_local_driver(webdriver, service_cls, chrome_options, project_root, logger):
    last_error = None
    for driver_path in resolve_local_driver_paths(project_root):
        try:
            _log(logger, "info", f"📦 优先尝试本地驱动: {driver_path}")
            driver = webdriver.Chrome(service=service_cls(driver_path), options=chrome_options)
            _log(logger, "info", "✅ 本地驱动初始化成功")
            return driver, None
        except Exception as e:
            last_error = e
            _log(logger, "warning", f"⚠️ 本地驱动不可用: {str(e)[:120]}")
    return None, last_error


def _create_chrome_with_manager(webdriver, service_cls, manager_cls, chrome_options, logger):
    try:
        _log(logger, "info", "🌐 尝试使用 webdriver-manager 下载 ChromeDriver...")
        os.environ["WDM_SSL_VERIFY"] = "0"
        service = service_cls(manager_cls().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        _log(logger, "info", "✅ webdriver-manager 初始化成功")
        return driver, None
    except Exception as e:
        _log(logger, "warning", f"⚠️ webdriver-manager 初始化失败: {str(e)[:120]}")
        return None, e


def _create_chrome_with_selenium_manager(webdriver, chrome_options, logger):
    try:
        _log(logger, "info", "🔄 尝试使用 Selenium Manager 自动配置驱动...")
        driver = webdriver.Chrome(options=chrome_options)
        _log(logger, "info", "✅ Selenium Manager 初始化成功")
        return driver, None
    except Exception as e:
        _log(logger, "warning", f"⚠️ Selenium Manager 初始化失败: {str(e)[:120]}")
        return None, e


def _create_chrome_from_path_probe(webdriver, chrome_options, logger):
    try:
        result = subprocess.run(["chromedriver", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return None, RuntimeError("chromedriver --version failed")
        _log(logger, "info", f"🔍 找到系统 ChromeDriver: {result.stdout.strip()}")
        driver = webdriver.Chrome(options=chrome_options)
        _log(logger, "info", "✅ 系统 PATH ChromeDriver 初始化成功")
        return driver, None
    except Exception as e:
        _log(logger, "warning", f"⚠️ 系统 PATH ChromeDriver 初始化失败: {str(e)[:120]}")
        return None, e


def _create_edge_fallback(webdriver, edge_options, project_root, last_error, logger):
    _log(logger, "error", f"❌ ChromeDriver 初始化失败: {last_error}")
    _log(logger, "error", "🔄 尝试回退到 Edge 浏览器...")
    try:
        driver = webdriver.Edge(options=edge_options)
        _log(logger, "info", "✅ Edge 初始化成功，已自动切换为 Edge 继续运行")
        return driver
    except Exception as edge_error:
        _log(logger, "error", f"❌ Edge 初始化失败: {edge_error}")
        _log(logger, "error", "请下载与本机 Chrome 主版本一致的 chromedriver.exe")
        _log(logger, "error", "下载地址: https://registry.npmmirror.com/binary.html?path=chromedriver/")
        _log(logger, "error", f"建议放置路径: {Path(project_root) / 'code' / 'chromedriver.exe'}")
        raise RuntimeError(f"ChromeDriver初始化失败: {last_error}")


def create_browser_session(
    project_root,
    headless=False,
    logger=None,
    window_size="1349,768",
    user_agent=DEFAULT_CHROME_USER_AGENT,
    wait_seconds=30,
    retry_clean_manager=False,
    check_path_driver=False,
):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager

    chrome_options = build_chrome_options(headless=headless, window_size=window_size, user_agent=user_agent)
    edge_options = build_edge_options(headless=headless, window_size=window_size)

    driver = None
    last_error = None

    driver, last_error = _create_chrome_with_local_driver(
        webdriver, Service, chrome_options, project_root, logger
    )

    if driver is None:
        driver, last_error = _create_chrome_with_manager(
            webdriver, Service, ChromeDriverManager, chrome_options, logger
        )

    if driver is None and retry_clean_manager:
        shutil.rmtree(Path.home() / ".wdm", ignore_errors=True)
        driver, last_error = _create_chrome_with_manager(
            webdriver, Service, ChromeDriverManager, chrome_options, logger
        )

    if driver is None:
        driver, last_error = _create_chrome_with_selenium_manager(webdriver, chrome_options, logger)

    if driver is None and check_path_driver:
        driver, last_error = _create_chrome_from_path_probe(webdriver, chrome_options, logger)

    browser_name = "chrome"
    if driver is None:
        driver = _create_edge_fallback(webdriver, edge_options, project_root, last_error, logger)
        browser_name = "edge"

    hide_webdriver_flag(driver, logger=logger)
    wait = WebDriverWait(driver, wait_seconds)
    _log(logger, "info", "浏览器驱动初始化完成")
    return BrowserSession(driver=driver, wait=wait, browser_name=browser_name)

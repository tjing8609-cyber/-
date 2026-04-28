from selenium.webdriver.common.by import By

from element_actions import click_element, scroll_page_to_load, switch_to_latest_window
from page_detection import close_common_dialogs, try_click_enter_study


def course_name_selectors(course_name, include_history_fallback=False):
    name = str(course_name or "").strip()
    selectors = [
        f"//*[contains(text(), '{name}')]",
        f"//div[contains(text(), '{name}')]",
        f"//a[contains(text(), '{name}')]",
        f"//span[contains(text(), '{name}')]",
        f"//h3[contains(text(), '{name}')]",
        f"//h4[contains(text(), '{name}')]",
        f"//p[contains(text(), '{name}')]",
        f"//div[contains(@class, 'course')]//*[contains(text(), '{name}')]",
        f"//div[contains(@class, 'card')]//*[contains(text(), '{name}')]",
    ]
    if include_history_fallback:
        selectors.extend([
            "//*[contains(text(), '中国近现代史')]",
            "//*[contains(text(), '近现代史纲要')]",
        ])
    return selectors


def is_browser_alive(driver, logger=None):
    try:
        current_url = driver.current_url
        if logger:
            logger.info(f"当前页面URL: {current_url}")
        return True
    except Exception as e:
        if logger:
            logger.error("⚠️  浏览器已关闭！请不要手动关闭浏览器窗口！")
            logger.error(f"错误详情: {e}")
        return False


def find_course_elements(driver, selector):
    try:
        return driver.find_elements(By.XPATH, selector)
    except Exception:
        return []


def find_and_click_course_by_name(
    driver,
    course_name,
    logger=None,
    wait_func=None,
    selectors=None,
    include_history_fallback=False,
    scroll_passes=3,
    wait_after_click=5,
):
    if not course_name:
        return False
    if logger:
        logger.info(f"正在查找'{course_name}'课程...")
    if not is_browser_alive(driver, logger=logger):
        return False

    if logger:
        logger.info("滚动页面加载所有课程...")
    scroll_page_to_load(driver, wait_func=wait_func, passes=scroll_passes, delay=1)

    course_selectors = selectors or course_name_selectors(
        course_name,
        include_history_fallback=include_history_fallback,
    )
    for selector_idx, selector in enumerate(course_selectors, 1):
        if logger:
            logger.info(f"尝试课程选择器 {selector_idx}/{len(course_selectors)}: {selector[:80]}...")
        elements = find_course_elements(driver, selector)
        if not elements:
            if logger:
                logger.info(f"选择器 {selector_idx} 未找到元素")
            continue

        if logger:
            logger.info(f"选择器 {selector_idx} 找到 {len(elements)} 个匹配元素")
        for idx, element in enumerate(elements):
            try:
                elem_text = element.text[:50] if element.text else "(无文本)"
                if logger:
                    logger.info(f"尝试课程元素 {idx + 1}/{len(elements)}: {elem_text}")
                if click_element(driver, element, logger=logger, wait_func=wait_func, wait_seconds=wait_after_click):
                    if logger:
                        logger.info(f"✅ 成功点击'{course_name}'课程")
                    return True
            except Exception as e:
                if logger:
                    logger.warning(f"处理课程元素 {idx + 1} 时出错: {e}")
                continue

    if logger:
        logger.error(f"未找到'{course_name}'课程")
        logger.error("请检查：")
        logger.error("1. 课程名称是否正确（当前配置：'" + str(course_name) + "'）")
        logger.error("2. 是否需要先点击某个标签页（如'共享课'）")
    return False


def enter_study_page(driver, logger=None, wait_func=None, close_dialogs_func=None):
    if logger:
        logger.info("进入学习页面...")
    switch_to_latest_window(driver)
    if wait_func:
        wait_func(3)

    clicked = try_click_enter_study(driver, logger=logger, wait_func=wait_func)
    if not clicked and logger:
        logger.info("未找到继续学习按钮，可能已在学习页面")

    switch_to_latest_window(driver)
    if wait_func:
        wait_func(3)
    try:
        if logger:
            logger.info(f"✅ 当前页面: {driver.current_url}")
    except Exception:
        pass

    if close_dialogs_func is not None:
        try:
            close_dialogs_func()
        except Exception:
            close_common_dialogs(driver, logger=logger)
    else:
        close_common_dialogs(driver, logger=logger)
    return True

import datetime
from dataclasses import dataclass, field

from course_catalog import classify_catalog_text
from course_outline import expand_collapsed_chapters, find_outline_scroll_container
from video_catalog import is_catalog_video_completed, video_title_from_text


DEFAULT_SIDEBAR_SELECTORS = [
    "//div[contains(@class, 'catalog')]",
    "//div[contains(@class, 'sidebar')]",
    "//div[contains(@class, 'directory')]",
    "//aside",
]
EXTENDED_SIDEBAR_SELECTORS = [
    "//div[contains(@class, 'box-right')]",
    "//div[contains(@class, 'catalog_box')]",
    *DEFAULT_SIDEBAR_SELECTORS,
]
DEFAULT_SIDEBAR_VIDEO_SELECTORS = [
    ".//div[contains(@class, 'video') or contains(@class, 'lesson')]",
    ".//li[contains(@class, 'video') or contains(@class, 'lesson')]",
    ".//a[contains(@class, 'video') or contains(@class, 'lesson')]",
    ".//*[contains(text(), '视频')]",
    ".//div[contains(@class, 'item')]",
    ".//div[contains(@class, 'chapter-item')]",
]
EXTENDED_SIDEBAR_VIDEO_SELECTORS = [
    ".//li[contains(@class, 'clearfix')]",
    ".//div[contains(@class, 'video') or contains(@class, 'lesson')]",
    ".//li[contains(@class, 'video') or contains(@class, 'lesson')]",
    ".//a[contains(@class, 'video') or contains(@class, 'lesson')]",
    ".//*[contains(@class, 'catalog_title')]",
    ".//div[contains(@class, 'item')]",
    ".//div[contains(@class, 'chapter-item')]",
    ".//span[contains(@class, 'catalog_title')]",
    ".//li",
]
MAIN_AREA_VIDEO_SELECTORS = [
    "//a[contains(@href, 'video') or contains(@href, 'play') or contains(@href, 'watch')]",
    "//a[contains(text(), '.mp4') or contains(text(), '.MP4')]",
    "//a[contains(@class, 'video')]",
    "//a[contains(@class, 'lesson')]",
    "//a[contains(@class, 'chapter')]",
    "//div[@onclick and (contains(@class, 'video') or contains(@class, 'lesson'))]",
    "//li[@onclick and (contains(@class, 'video') or contains(@class, 'lesson'))]",
    "//div[contains(@class, 'video-item') or contains(@class, 'lesson-item')]",
    "//li[contains(@class, 'video-item') or contains(@class, 'lesson-item')]",
    "//*[contains(text(), '.mp4') or contains(text(), '.MP4')]/ancestor::a",
    "//*[contains(text(), '.mp4') or contains(text(), '.MP4')]/parent::*[self::a or @onclick]",
    "//*[contains(text(), '.mp4') or contains(text(), '.MP4')]",
    "//a[@href]",
    "//div[@onclick]",
    "//li[@onclick]",
]
SKIP_TEXT_MARKERS = [
    ".pptx",
    ".ppt",
    ".pdf",
    "作业",
    "见面课",
    "课程问答",
    "课程表",
    "成绩分析",
    "课程资料",
    "平时测试",
]


@dataclass
class VideoDiscoveryResult:
    unwatched: list = field(default_factory=list)
    watched: list = field(default_factory=list)
    skipped: int = 0


def _log(logger, level, message):
    if logger is None:
        return
    getattr(logger, level)(message)


def safe_element_text(element):
    try:
        return element.text or ""
    except Exception:
        return ""


def is_interactable(element):
    try:
        return element.is_displayed() and element.is_enabled()
    except Exception:
        return False


def find_visible_sidebar(driver, selectors=None, logger=None):
    for selector in selectors or DEFAULT_SIDEBAR_SELECTORS:
        try:
            sidebar = driver.find_element("xpath", selector)
            if sidebar and sidebar.is_displayed():
                _log(logger, "info", f"✅ 找到右侧目录: {selector}")
                return sidebar
        except Exception:
            continue
    return None


def collect_elements_by_selectors(root, selectors, logger=None, log_empty=False):
    elements = []
    for selector in selectors:
        try:
            found = root.find_elements("xpath", selector)
            if found:
                _log(logger, "info", f"✅ 选择器 '{selector}' 找到 {len(found)} 个元素")
                elements.extend(found)
            elif log_empty:
                _log(logger, "debug", f"⚠️  选择器 '{selector}' 未找到元素")
        except Exception as e:
            _log(logger, "debug", f"❌ 选择器 '{selector}' 失败: {e}")
    return elements


def scroll_sidebar_simple(driver, sidebar, logger=None, wait_func=None, passes=5):
    _log(logger, "info", "滚动侧边栏加载所有视频...")
    for index in range(passes):
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", sidebar)
        if wait_func:
            wait_func(1)
        _log(logger, "info", f"滚动进度: {index + 1}/{passes}")
    driver.execute_script("arguments[0].scrollTop = 0;", sidebar)
    if wait_func:
        wait_func(2)


def scroll_sidebar_with_wheel(driver, scroll_container, logger=None, wait_func=None, max_scroll_attempts=20):
    _log(logger, "info", "🔄 开始使用鼠标滚轮模拟滚动...")
    scroll_no_change_count = 0
    for index in range(max_scroll_attempts):
        scroll_before = driver.execute_script("return arguments[0].scrollTop;", scroll_container)
        driver.execute_script(
            """
            var element = arguments[0];
            var wheelEvent = new WheelEvent('wheel', {
                deltaY: 500,
                bubbles: true,
                cancelable: true
            });
            element.dispatchEvent(wheelEvent);
            element.scrollTop = element.scrollTop + 500;
            """,
            scroll_container,
        )
        if wait_func:
            wait_func(0.8)
        scroll_after = driver.execute_script("return arguments[0].scrollTop;", scroll_container)
        scroll_height = driver.execute_script("return arguments[0].scrollHeight;", scroll_container)
        _log(
            logger,
            "info",
            f"  滚动 {index + 1}/{max_scroll_attempts}: {scroll_before}px → {scroll_after}px (总高度: {scroll_height}px)",
        )
        if scroll_after == scroll_before:
            scroll_no_change_count += 1
            _log(logger, "debug", f"  ⚠️  滚动位置未变化 ({scroll_no_change_count}/3)")
            if scroll_no_change_count >= 3:
                _log(logger, "info", "  ✅ 滚动位置连续3次未变化，已到达底部")
                break
        else:
            scroll_no_change_count = 0
        if scroll_after >= scroll_height - 100:
            _log(logger, "info", "  ✅ 已滚动到底部，提前结束滚动")
            break

    _log(logger, "info", "✅ 滚动完成，等待内容加载...")
    if wait_func:
        wait_func(2)
    driver.execute_script("arguments[0].scrollTop = 0;", scroll_container)
    if wait_func:
        wait_func(1)


def write_debug_html(element, debug_html_path, logger=None):
    if not debug_html_path:
        return
    try:
        with open(debug_html_path, "w", encoding="utf-8") as file:
            file.write(element.get_attribute("outerHTML") or "")
        _log(logger, "warning", f"⚠️  未找到任何视频元素，已保存侧边栏HTML到 {debug_html_path}")
    except Exception as e:
        _log(logger, "debug", f"保存HTML失败: {e}")


def write_debug_page(driver, debug_html_path=None, logger=None):
    try:
        if debug_html_path is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_html_path = f"debug_page_{timestamp}.html"
        with open(debug_html_path, "w", encoding="utf-8") as file:
            file.write(driver.page_source)
        _log(logger, "warning", f"⚠️  未找到任何视频元素，已保存页面HTML到: {debug_html_path}")
        _log(logger, "warning", "🔍 请打开此文件查看页面结构，找到视频元素的class或id")
    except Exception as e:
        _log(logger, "error", f"保存页面HTML失败: {e}")


def scroll_main_area_for_videos(driver, logger=None, wait_func=None, passes=5):
    _log(logger, "info", "滚动页面加载所有视频...")
    for index in range(passes):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        if wait_func:
            wait_func(2)
        _log(logger, "info", f"滚动进度: {index + 1}/{passes}")
    driver.execute_script("window.scrollTo(0, 0);")
    if wait_func:
        wait_func(2)


def collect_driver_elements_by_selectors(driver, selectors, logger=None):
    elements = []
    for selector in selectors:
        try:
            found = driver.find_elements("xpath", selector)
            if found:
                _log(logger, "info", f"选择器 {selector} 找到 {len(found)} 个元素")
                elements.extend(found)
        except Exception as e:
            _log(logger, "warning", f"选择器 {selector} 失败: {e}")
    return elements


def discover_main_area_videos(
    driver,
    completed_texts=None,
    logger=None,
    wait_func=None,
    video_selectors=None,
    debug_html_path=None,
):
    if wait_func:
        wait_func(5)
    try:
        _log(logger, "info", f"视频列表页面URL: {driver.current_url}")
    except Exception:
        pass

    scroll_main_area_for_videos(driver, logger=logger, wait_func=wait_func)
    _log(logger, "info", "开始查找视频元素...")
    all_video_elements = collect_driver_elements_by_selectors(
        driver,
        video_selectors or MAIN_AREA_VIDEO_SELECTORS,
        logger=logger,
    )
    _log(logger, "info", f"总共找到 {len(all_video_elements)} 个可能的视频元素")
    if not all_video_elements:
        write_debug_page(driver, debug_html_path=debug_html_path, logger=logger)

    unique_elements = dedupe_elements_by_text(all_video_elements)
    _log(logger, "info", f"去重后剩余 {len(unique_elements)} 个元素")
    return scan_video_candidates(
        unique_elements,
        completed_texts=completed_texts,
        logger=logger,
        require_mp4=True,
        prefer_inner_link=True,
    )


def discover_sidebar_videos(
    driver,
    completed_texts=None,
    logger=None,
    wait_func=None,
    sidebar_selectors=None,
    video_selectors=None,
    expand_chapters=True,
    use_wheel_scroll=False,
    include_watched=False,
    debug_html_path=None,
):
    sidebar = find_visible_sidebar(driver, selectors=sidebar_selectors, logger=logger)
    if not sidebar:
        return None

    if expand_chapters:
        expand_collapsed_chapters(
            driver,
            sidebar,
            logger=logger,
            wait_func=wait_func,
            max_passes=8,
        )

    if use_wheel_scroll:
        scroll_container = find_outline_scroll_container(sidebar)
        if scroll_container is sidebar:
            _log(logger, "info", "使用侧边栏本身作为滚动容器")
        else:
            _log(logger, "info", "✅ 找到滚动容器")
        scroll_sidebar_with_wheel(driver, scroll_container, logger=logger, wait_func=wait_func)
    else:
        scroll_sidebar_simple(driver, sidebar, logger=logger, wait_func=wait_func)

    _log(logger, "info", "🔍 开始查找视频元素...")
    all_video_elements = collect_elements_by_selectors(
        sidebar,
        video_selectors or DEFAULT_SIDEBAR_VIDEO_SELECTORS,
        logger=logger,
        log_empty=use_wheel_scroll,
    )
    unique_elements = list(dict.fromkeys(all_video_elements))
    _log(logger, "info", f"📋 总共找到 {len(unique_elements)} 个去重后的视频元素")
    if not unique_elements:
        write_debug_html(sidebar, debug_html_path, logger=logger)

    return scan_video_candidates(
        unique_elements,
        completed_texts=completed_texts,
        logger=logger,
        record_watched=include_watched,
    )


def is_skippable_video_text(text, require_mp4=False):
    normalized = text or ""
    lowered = normalized.lower()
    if require_mp4 and ".mp4" not in lowered:
        return True, "non-mp4 item"
    for marker in SKIP_TEXT_MARKERS:
        if marker.lower() in lowered or marker in normalized:
            return True, f"skip marker: {marker}"
    return False, ""


def clickable_video_element(element, prefer_inner_link=False):
    if not prefer_inner_link:
        return element
    try:
        tag_name = (element.tag_name or "").lower()
    except Exception:
        tag_name = ""
    if tag_name == "a":
        return element
    try:
        link = element.find_element("xpath", ".//a")
        if is_interactable(link):
            return link
    except Exception:
        pass
    return element


def add_watched_record(watched, text):
    title = video_title_from_text(text, max_length=50)
    if not title:
        return
    if not any(item.get("title") == title for item in watched):
        watched.append({"text": text[:100], "title": title})


def scan_video_candidates(
    elements,
    completed_texts=None,
    logger=None,
    require_mp4=False,
    prefer_inner_link=False,
    record_watched=True,
):
    completed_texts = set(completed_texts or [])
    result = VideoDiscoveryResult()

    for index, element in enumerate(elements or []):
        try:
            text = safe_element_text(element).strip()
            if not text or len(text) < 3:
                result.skipped += 1
                continue

            classification = classify_catalog_text(text)
            if not classification.is_video:
                _log(logger, "debug", f"  → 跳过：{classification.reason} ({text[:30]}...)")
                result.skipped += 1
                continue

            skippable, reason = is_skippable_video_text(text, require_mp4=require_mp4)
            if skippable:
                _log(logger, "debug", f"  → 跳过：{reason} ({text[:30]}...)")
                result.skipped += 1
                continue

            if is_catalog_video_completed(element, logger=logger):
                _log(logger, "debug", f"  → 跳过：已完成 ({text[:30]}...)")
                if record_watched:
                    add_watched_record(result.watched, text)
                result.skipped += 1
                continue

            if text in completed_texts:
                _log(logger, "debug", f"  → 跳过：已记录 ({text[:30]}...)")
                result.skipped += 1
                continue

            target = clickable_video_element(element, prefer_inner_link=prefer_inner_link)
            if is_interactable(target):
                result.unwatched.append({"element": target, "text": text[:100]})
                _log(logger, "info", f"  → ✅ 找到未观看视频: {text[:50]}...")
            else:
                result.skipped += 1
        except Exception as e:
            _log(logger, "debug", f"处理视频元素 {index + 1} 时出错: {e}")
            result.skipped += 1

    return result


def dedupe_elements_by_text(elements, min_length=3):
    unique = []
    seen = set()
    for element in elements or []:
        text = safe_element_text(element).strip()
        if text and len(text) >= min_length and text not in seen:
            seen.add(text)
            unique.append(element)
    return unique


__all__ = [
    "DEFAULT_SIDEBAR_SELECTORS",
    "DEFAULT_SIDEBAR_VIDEO_SELECTORS",
    "EXTENDED_SIDEBAR_SELECTORS",
    "EXTENDED_SIDEBAR_VIDEO_SELECTORS",
    "MAIN_AREA_VIDEO_SELECTORS",
    "VideoDiscoveryResult",
    "clickable_video_element",
    "collect_elements_by_selectors",
    "dedupe_elements_by_text",
    "discover_main_area_videos",
    "discover_sidebar_videos",
    "find_visible_sidebar",
    "is_skippable_video_text",
    "scan_video_candidates",
]

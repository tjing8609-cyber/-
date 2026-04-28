#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Utilities for resilient course outline traversal."""

import re
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException


CHAPTER_RE = re.compile(r"第[一二三四五六七八九十百千万0-9]+章[:：]?")
LESSON_RE = re.compile(r"(?<!\d)\d+\.\d+(?:\.\d+)?")


def find_outline_scroll_container(sidebar):
    """Return the element that actually scrolls inside a course outline."""
    selectors = [
        ".//*[contains(@class, 'el-scrollbar__wrap')]",
        ".//*[contains(@class, 'scrollbar-wrap') or contains(@class, 'scroll-wrap')]",
        ".//*[contains(@class, 'scroll') and (contains(@class, 'wrap') or contains(@class, 'body'))]",
    ]
    for selector in selectors:
        try:
            element = sidebar.find_element(By.XPATH, selector)
            if element:
                return element
        except Exception:
            continue
    return sidebar


def _log(logger, level, message):
    if logger is None:
        return
    getattr(logger, level)(message)


def _wait(wait_func, seconds):
    if wait_func is None:
        return
    wait_func(seconds)


def _lesson_count(sidebar):
    try:
        text = sidebar.text or ""
    except StaleElementReferenceException:
        return 0
    return len(LESSON_RE.findall(text))


def _is_chapter_header_text(text):
    if not text:
        return False
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not CHAPTER_RE.search(normalized):
        return False
    if LESSON_RE.search(normalized):
        return False
    if any(keyword in normalized for keyword in ["测试", "作业", "课程问答", "成绩分析"]):
        return False
    return len(normalized) <= 120 and len(normalized.splitlines()) <= 4


def _chapter_candidates(sidebar):
    selectors = [
        ".//*[self::div or self::li or self::span or self::button or self::p]"
        "[contains(normalize-space(.), '第') and contains(normalize-space(.), '章')]",
    ]
    elements = []
    for selector in selectors:
        try:
            elements.extend(sidebar.find_elements(By.XPATH, selector))
        except Exception:
            continue
    return list(dict.fromkeys(elements))


def _clickable_target(driver, element):
    try:
        return driver.execute_script(
            """
            var el = arguments[0];
            var original = el;
            for (var i = 0; el && i < 4; i++, el = el.parentElement) {
              var style = window.getComputedStyle(el);
              var role = el.getAttribute('role') || '';
              var cls = String(el.className || '');
              if (el.onclick || role === 'button' || style.cursor === 'pointer' ||
                  /chapter|catalog|title|item|section|collapse|fold|tree|node/i.test(cls)) {
                return el;
              }
            }
            return original;
            """,
            element,
        )
    except Exception:
        return element


def _click(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    except Exception:
        pass
    try:
        actions = ActionChains(driver)
        actions.move_to_element(element)
        actions.pause(0.2)
        actions.click()
        actions.perform()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False


def _scroll_down(driver, element):
    try:
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
            return [element.scrollTop, element.scrollHeight];
            """,
            element,
        )
        return True
    except Exception:
        return False


def expand_collapsed_chapters(driver, sidebar, logger=None, wait_func=None, max_passes=6):
    """Expand visible collapsed chapters in a course outline.

    The new Zhidao layout only renders lessons under an expanded chapter. This
    helper cautiously clicks chapter headers and compares visible lesson counts;
    if a click collapses an already-open chapter, it clicks again to restore it.
    """
    scroll_container = find_outline_scroll_container(sidebar)
    expanded = 0
    seen_headers = set()

    _log(logger, "info", "🔎 检查是否存在折叠章节...")
    try:
        driver.execute_script("arguments[0].scrollTop = 0;", scroll_container)
    except Exception:
        pass
    _wait(wait_func, 0.5)

    for pass_index in range(max_passes):
        changed_this_pass = 0
        candidates = _chapter_candidates(sidebar)
        _log(logger, "debug", f"第 {pass_index + 1} 轮检测到 {len(candidates)} 个章节候选")

        for candidate in candidates:
            try:
                text = (candidate.text or "").strip()
                if not _is_chapter_header_text(text):
                    continue
                key = " ".join(text.split())
                if key in seen_headers:
                    continue
                seen_headers.add(key)

                target = _clickable_target(driver, candidate)
                before = _lesson_count(sidebar)
                if not _click(driver, target):
                    continue
                _wait(wait_func, 0.8)
                after = _lesson_count(sidebar)

                if after > before:
                    expanded += 1
                    changed_this_pass += 1
                    _log(logger, "info", f"✅ 已展开章节: {key[:40]}")
                elif after < before:
                    _log(logger, "debug", f"章节已是展开状态，恢复: {key[:40]}")
                    _click(driver, target)
                    _wait(wait_func, 0.5)
                else:
                    _log(logger, "debug", f"章节点击后条目数未变化: {key[:40]}")
            except StaleElementReferenceException:
                continue
            except Exception as exc:
                _log(logger, "debug", f"展开章节候选失败: {exc}")

        if not _scroll_down(driver, scroll_container):
            break
        _wait(wait_func, 0.8)

        if changed_this_pass == 0 and pass_index >= 2:
            # Three passes without new expansions usually means the current
            # outline window has been exhausted.
            break

    try:
        driver.execute_script("arguments[0].scrollTop = 0;", scroll_container)
    except Exception:
        pass
    _wait(wait_func, 0.5)
    _log(logger, "info", f"📚 章节展开检查完成，新增展开 {expanded} 个章节")
    return expanded

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from video_discovery import (  # noqa: E402
    collect_elements_by_selectors,
    dedupe_elements_by_text,
    discover_main_area_videos,
    discover_sidebar_videos,
    is_skippable_video_text,
    scan_video_candidates,
)


class FakeElement:
    def __init__(self, text="", displayed=True, enabled=True, tag_name="div", children=None):
        self.text = text
        self.displayed = displayed
        self.enabled = enabled
        self.tag_name = tag_name
        self.children = children or {}

    def is_displayed(self):
        return self.displayed

    def is_enabled(self):
        return self.enabled

    def find_elements(self, by, value):
        return self.children.get(value, [])

    def find_element(self, by, value):
        items = self.find_elements(by, value)
        if items:
            return items[0]
        raise RuntimeError("not found")


class FakeDriver:
    def __init__(self, elements=None, current_url="", page_source=""):
        self.elements = elements or {}
        self.scripts = []
        self.current_url = current_url
        self.page_source = page_source

    def find_element(self, by, value):
        items = self.elements.get(value, [])
        if items:
            return items[0]
        raise RuntimeError("not found")

    def find_elements(self, by, value):
        return self.elements.get(value, [])

    def execute_script(self, script, *args):
        self.scripts.append((script, args))
        return 0


class VideoDiscoveryTests(unittest.TestCase):
    def test_skips_documents_and_assignments(self):
        self.assertTrue(is_skippable_video_text("课程资料.ppt")[0])
        self.assertTrue(is_skippable_video_text("章节作业")[0])
        self.assertFalse(is_skippable_video_text("1.1 绪论 00:10")[0])

    def test_requires_mp4_when_requested(self):
        self.assertTrue(is_skippable_video_text("1.1 绪论 00:10", require_mp4=True)[0])
        self.assertFalse(is_skippable_video_text("1.1 绪论.mp4 00:10", require_mp4=True)[0])

    def test_scan_video_candidates_returns_unwatched(self):
        element = FakeElement("1.1 绪论 00:10")

        result = scan_video_candidates([element])

        self.assertEqual(len(result.unwatched), 1)
        self.assertIs(result.unwatched[0]["element"], element)

    def test_scan_video_candidates_records_watched(self):
        element = FakeElement("1.1 绪论 100% 00:10")

        result = scan_video_candidates([element])

        self.assertEqual(result.unwatched, [])
        self.assertEqual(result.watched[0]["title"], "1.1 绪论")

    def test_scan_video_candidates_can_include_completed_for_replay(self):
        element = FakeElement("1.1 缁 100% 00:10")

        result = scan_video_candidates([element], include_completed=True)

        self.assertEqual(len(result.unwatched), 1)
        self.assertIs(result.unwatched[0]["element"], element)
        self.assertEqual(result.watched[0]["title"], "1.1 缁")

    def test_scan_video_candidates_can_include_recorded_completed_for_replay(self):
        element = FakeElement("1.1 缁 00:10")

        result = scan_video_candidates(
            [element],
            completed_texts=["1.1 缁 00:10"],
            include_completed=True,
        )

        self.assertEqual(len(result.unwatched), 1)
        self.assertIs(result.unwatched[0]["element"], element)

    def test_prefer_inner_link(self):
        link = FakeElement("1.1 绪论.mp4 00:10", tag_name="a")
        wrapper = FakeElement("1.1 绪论.mp4 00:10", children={".//a": [link]})

        result = scan_video_candidates([wrapper], require_mp4=True, prefer_inner_link=True)

        self.assertIs(result.unwatched[0]["element"], link)

    def test_dedupe_elements_by_text(self):
        first = FakeElement("1.1 绪论")
        duplicate = FakeElement("1.1 绪论")
        second = FakeElement("1.2 背景")

        self.assertEqual(dedupe_elements_by_text([first, duplicate, second]), [first, second])

    def test_collect_elements_by_selectors(self):
        first = FakeElement("1.1 绪论")
        second = FakeElement("1.2 背景")
        root = FakeElement(children={
            ".//li": [first],
            ".//div": [second],
        })

        self.assertEqual(collect_elements_by_selectors(root, [".//li", ".//div"]), [first, second])

    def test_discover_sidebar_videos(self):
        video = FakeElement("1.1 绪论 00:10")
        sidebar = FakeElement(children={".//li": [video]})
        driver = FakeDriver({"//aside": [sidebar]})

        result = discover_sidebar_videos(
            driver,
            sidebar_selectors=["//aside"],
            video_selectors=[".//li"],
            expand_chapters=False,
        )

        self.assertEqual(len(result.unwatched), 1)
        self.assertIs(result.unwatched[0]["element"], video)

    def test_discover_sidebar_videos_returns_none_without_sidebar(self):
        result = discover_sidebar_videos(FakeDriver(), sidebar_selectors=["//aside"], expand_chapters=False)

        self.assertIsNone(result)

    def test_discover_main_area_videos(self):
        video = FakeElement("1.1 绪论.mp4 00:10", tag_name="a")
        driver = FakeDriver({
            "//a[contains(text(), '.mp4') or contains(text(), '.MP4')]": [video]
        }, current_url="https://example.com/study")

        result = discover_main_area_videos(driver, wait_func=lambda _seconds: None)

        self.assertEqual(len(result.unwatched), 1)
        self.assertIs(result.unwatched[0]["element"], video)


    def test_discover_main_area_videos_can_skip_mp4_requirement_for_replay(self):
        video = FakeElement("1.1 replay title 00:10", tag_name="a")
        driver = FakeDriver({
            "//a[contains(text(), '.mp4') or contains(text(), '.MP4')]": [video]
        }, current_url="https://example.com/study")

        result = discover_main_area_videos(
            driver,
            wait_func=lambda _seconds: None,
            require_mp4=False,
        )

        self.assertEqual(len(result.unwatched), 1)
        self.assertIs(result.unwatched[0]["element"], video)


if __name__ == "__main__":
    unittest.main()

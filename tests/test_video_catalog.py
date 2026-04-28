import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from video_catalog import (  # noqa: E402
    element_context_chain,
    is_catalog_video_completed,
    progress_state_from_text,
    video_title_from_text,
)


class FakeElement:
    def __init__(self, text="", children=None, parent=None):
        self.text = text
        self.children = children or {}
        self.parent = parent

    def find_elements(self, by, value):
        return self.children.get(value, [])

    def find_element(self, by, value):
        if value in ("./parent::*", "./..") and self.parent is not None:
            return self.parent
        raise RuntimeError("not found")


class VideoCatalogTests(unittest.TestCase):
    def test_progress_state_from_text(self):
        self.assertEqual(progress_state_from_text("1.1 100% 00:01:20"), "completed")
        self.assertEqual(progress_state_from_text("1.1 17% 00:01:20"), "partial")
        self.assertEqual(progress_state_from_text("1.1 00:01:20"), "unknown")

    def test_completed_by_text_marker(self):
        self.assertTrue(is_catalog_video_completed(FakeElement("1.1 绪论 已完成")))

    def test_partial_progress_is_not_completed(self):
        self.assertFalse(is_catalog_video_completed(FakeElement("1.1 绪论 56% 00:10")))

    def test_completed_marker_can_live_on_parent(self):
        marker_xpath = (
            ".//*[contains(@class, 'zhihuishu-wancheng') "
            "or contains(@class, 'time_icofinish') "
            "or contains(@class, 'complete') "
            "or contains(@class, 'finish') "
            "or contains(@class, 'done')]"
        )
        parent = FakeElement(children={marker_xpath: [FakeElement()]})
        child = FakeElement("1.1 绪论", parent=parent)

        self.assertTrue(is_catalog_video_completed(child))
        self.assertEqual(element_context_chain(child), [child, parent])

    def test_unwatched_marker_wins_over_completed_marker(self):
        unwatched_xpath = ".//*[contains(@class, 'zhihuishu-weikaishi')]"
        element = FakeElement("1.1 绪论 100%", children={unwatched_xpath: [FakeElement()]})

        self.assertFalse(is_catalog_video_completed(element))

    def test_video_title_from_text_removes_progress_and_duration(self):
        self.assertEqual(video_title_from_text("1.1 绪论\n56%\n00:10:00"), "1.1 绪论")


if __name__ == "__main__":
    unittest.main()

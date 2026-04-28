import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from course_catalog import (  # noqa: E402
    classify_catalog_text,
    extract_catalog_title,
    looks_like_chapter_header,
)


class CourseCatalogTests(unittest.TestCase):
    def test_chapter_header_from_new_layout(self):
        text = "第二章:\n政治安全"

        self.assertTrue(looks_like_chapter_header(text))
        self.assertEqual(classify_catalog_text(text).kind, "chapter")

    def test_two_level_lesson_without_duration_is_video(self):
        text = "1.1 国家安全的内涵及重要性"

        result = classify_catalog_text(text)

        self.assertEqual(result.kind, "video")
        self.assertEqual(result.reason, "has lesson number")

    def test_multiline_lesson_without_duration_is_video(self):
        text = "1.3\n总体国家安全观的重要价值及涵盖领域"

        self.assertEqual(classify_catalog_text(text).kind, "video")

    def test_document_is_not_video(self):
        self.assertEqual(classify_catalog_text("课程资料.pptx").kind, "document")
        self.assertEqual(classify_catalog_text("讲义.pdf").kind, "document")

    def test_assignment_is_not_video(self):
        self.assertEqual(classify_catalog_text("第一章作业").kind, "assignment")

    def test_extract_title_removes_progress_and_duration(self):
        title = extract_catalog_title("2.1.6\n调节情绪\n11%\n00:07:14")

        self.assertEqual(title, "2.1.6 调节情绪")


if __name__ == "__main__":
    unittest.main()

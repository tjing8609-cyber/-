import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from agent.observer import infer_state_from_digest  # noqa: E402


def infer(text="", *, url="", title="", video_state=None, dialogs=None):
    return infer_state_from_digest(url, title, text, video_state=video_state, dialogs=dialogs)


class AgentObserverStateRulesTests(unittest.TestCase):
    def test_login_text_detects_login_state(self):
        state = infer("\u8bf7\u767b\u5f55 \u8d26\u53f7 \u5bc6\u7801")

        self.assertEqual(state.primary_state, "login")
        self.assertEqual(state.task_phase, "login")

    def test_course_home_text_detects_course_home(self):
        state = infer("\u6211\u7684\u8bfe\u7a0b \u8bfe\u7a0b\u5c01\u9762 \u8fdb\u5165\u5b66\u4e60 \u5b66\u4e60\u8fdb\u5ea6")

        self.assertEqual(state.primary_state, "course_home")

    def test_course_catalog_text_detects_course_catalog(self):
        state = infer("\u8bfe\u7a0b\u76ee\u5f55 \u7b2c\u4e00\u7ae0 \u7b2c\u4e00\u8282 \u672a\u5b66 \u7ee7\u7eed\u5b66\u4e60")

        self.assertEqual(state.primary_state, "course_catalog")

    def test_video_state_present_detects_video_page(self):
        state = infer(video_state={"present": True, "playing": True})

        self.assertEqual(state.primary_state, "video_page")
        self.assertGreaterEqual(state.confidence, 0.9)

    def test_video_url_weak_hit_detects_video_page(self):
        state = infer(url="https://example.com/studyvideo/123")

        self.assertEqual(state.primary_state, "video_page")
        self.assertGreaterEqual(state.confidence, 0.45)
        self.assertLessEqual(state.confidence, 0.6)

    def test_quiz_text_detects_quiz_page(self):
        state = infer("\u9898\u76ee 1. [\u5355\u9009\u9898] \u8bf7\u9009\u62e9 \u63d0\u4ea4\u7b54\u6848")

        self.assertEqual(state.primary_state, "quiz_page")

    def test_completed_text_detects_completed(self):
        state = infer("\u5b66\u4e60\u5b8c\u6210 \u8bfe\u7a0b\u5b8c\u6210")

        self.assertEqual(state.primary_state, "completed")
        self.assertEqual(state.task_phase, "done")

    def test_video_state_completed_detects_completed(self):
        state = infer(video_state={"present": True, "completed": True})

        self.assertEqual(state.primary_state, "completed")
        self.assertTrue(state.flags["video_completed"])

    def test_system_error_text_detects_error(self):
        state = infer("\u9875\u9762\u4e0d\u5b58\u5728 404 \u670d\u52a1\u5668\u9519\u8bef")

        self.assertEqual(state.primary_state, "error")
        self.assertTrue(state.flags["has_error_markers"])

    def test_wrong_answer_does_not_misclassify_as_system_error(self):
        state = infer("\u5224\u65ad\u9898 \u9519\u8bef\u7b54\u6848 \u8bf7\u9009\u62e9 \u63d0\u4ea4\u7b54\u6848")

        self.assertEqual(state.primary_state, "quiz_page")
        self.assertFalse(state.flags["has_error_markers"])

    def test_captcha_text_adds_captcha_overlay(self):
        state = infer("\u5b89\u5168\u9a8c\u8bc1 \u9a8c\u8bc1\u7801 \u6ed1\u5757")

        self.assertIn("captcha", state.overlays)
        self.assertTrue(state.flags["has_captcha"])

    def test_common_dialog_text_adds_common_dialog_overlay(self):
        state = infer("\u6e29\u99a8\u63d0\u793a \u6211\u77e5\u9053\u4e86 \u5173\u95ed")

        self.assertIn("common_dialog", state.overlays)
        self.assertTrue(state.flags["has_dialog"])

    def test_confirm_text_adds_confirm_dialog_overlay(self):
        state = infer("\u786e\u8ba4\u63d0\u4ea4 \u662f\u5426\u4ea4\u5377")

        self.assertIn("confirm_dialog", state.overlays)
        self.assertTrue(state.flags["has_confirm_markers"])

    def test_quiz_popup_text_adds_quiz_popup_overlay(self):
        state = infer("\u968f\u5802\u6d4b\u9a8c \u8bfe\u5802\u68c0\u6d4b\u9898 \u8bf7\u9009\u62e9")

        self.assertIn("quiz_popup", state.overlays)

    def test_loading_text_adds_loading_overlay(self):
        state = infer("\u6b63\u5728\u52a0\u8f7d loading \u8bf7\u7a0d\u5019")

        self.assertIn("loading", state.overlays)
        self.assertTrue(state.flags["has_loading_markers"])

    def test_video_playing_flag_from_video_state(self):
        state = infer(video_state={"present": True, "playing": True})

        self.assertTrue(state.flags["video_playing"])

    def test_video_completed_flag_from_video_state(self):
        state = infer(video_state={"present": True, "completed": True})

        self.assertTrue(state.flags["video_completed"])

    def test_dialogs_nonempty_sets_has_dialog(self):
        state = infer(dialogs=[{"text": "\u63d0\u793a", "role": "dialog"}])

        self.assertTrue(state.flags["has_dialog"])

    def test_quiz_markers_flag(self):
        state = infer("\u9898\u76ee \u591a\u9009\u9898 \u63d0\u4ea4\u7b54\u6848")

        self.assertTrue(state.flags["has_quiz_markers"])

    def test_course_markers_flag(self):
        state = infer("\u8bfe\u7a0b\u76ee\u5f55 \u7ae0\u8282 \u7ee7\u7eed\u5b66\u4e60")

        self.assertTrue(state.flags["has_course_markers"])

    def test_action_markers_set_clickable_candidates(self):
        state = infer("\u5f00\u59cb\u5b66\u4e60 \u64ad\u653e \u4e0b\u4e00\u8282")

        self.assertTrue(state.flags["has_clickable_candidates"])

    def test_course_catalog_maps_to_navigate_course_phase(self):
        state = infer("\u8bfe\u7a0b\u76ee\u5f55 \u7b2c\u4e00\u7ae0 \u7b2c\u4e00\u8282")

        self.assertEqual(state.task_phase, "navigate_course")

    def test_video_page_maps_to_watch_video_phase(self):
        state = infer(video_state={"present": True})

        self.assertEqual(state.task_phase, "watch_video")

    def test_video_page_with_quiz_popup_maps_to_handle_popup_phase(self):
        state = infer("\u968f\u5802\u6d4b\u9a8c \u9898\u76ee", video_state={"present": True})

        self.assertEqual(state.primary_state, "video_page")
        self.assertIn("quiz_popup", state.overlays)
        self.assertEqual(state.task_phase, "handle_popup")

    def test_quiz_page_maps_to_answer_quiz_phase(self):
        state = infer("\u9898\u76ee \u5355\u9009\u9898 \u63d0\u4ea4\u7b54\u6848")

        self.assertEqual(state.task_phase, "answer_quiz")

    def test_error_maps_to_error_phase(self):
        state = infer("500 error failed")

        self.assertEqual(state.task_phase, "error")

    def test_none_empty_input_is_unknown(self):
        state = infer_state_from_digest(None, None, None)

        self.assertEqual(state.primary_state, "unknown")
        self.assertEqual(state.task_phase, "unknown")

    def test_mixed_chinese_english_markers_work(self):
        state = infer("login \u8bf7\u767b\u5f55 password captcha")

        self.assertEqual(state.primary_state, "login")
        self.assertIn("captcha", state.overlays)

    def test_long_digest_does_not_break_inference(self):
        state = infer(("x" * 5000) + " \u8bfe\u7a0b\u76ee\u5f55 \u7ae0\u8282")

        self.assertEqual(state.primary_state, "course_catalog")

    def test_reason_is_non_empty_for_known_states(self):
        state = infer("\u8bfe\u7a0b\u76ee\u5f55 \u7ae0\u8282")

        self.assertTrue(state.reason)
        self.assertIn("matched", state.reason)

    def test_confidence_is_clamped(self):
        for state in [
            infer(""),
            infer("\u9898\u76ee \u5355\u9009\u9898 \u63d0\u4ea4\u7b54\u6848"),
            infer("500 error failed"),
            infer(video_state={"present": True}),
        ]:
            with self.subTest(state=state.primary_state):
                self.assertGreaterEqual(state.confidence, 0.0)
                self.assertLessEqual(state.confidence, 1.0)


if __name__ == "__main__":
    unittest.main()

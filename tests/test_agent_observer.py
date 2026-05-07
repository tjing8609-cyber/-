import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from agent.observer import (  # noqa: E402
    AgentObserver,
    ObserverOptions,
    extract_basic_driver_info,
    html_to_digest,
    infer_state_from_digest,
    normalize_dialogs,
    normalize_video_state,
    observe_to_event,
    safe_call,
    safe_getattr,
    safe_string,
)
from agent.schemas import AgentEvent, ObservationFrame, StateSnapshot  # noqa: E402


class FakeDriver:
    def __init__(self, url="https://example.com/course", title="课程页面", page_source="<html>课程目录 章节</html>"):
        self.current_url = url
        self.title = title
        self.page_source = page_source


class BrokenAttr:
    @property
    def bad(self):
        raise RuntimeError("bad attr")


class FakeMethods:
    def hello(self, name):
        return f"hello {name}"

    def explode(self):
        raise RuntimeError("boom")


class VideoObject:
    present = True
    duration = 100
    current_time = 30
    paused = False
    ended = False

    @property
    def playing(self):
        return True

    @property
    def completed(self):
        return False


class DialogObject:
    text = "AI随堂练习 判断题"
    role = "dialog"

    def is_displayed(self):
        return True


class AgentObserverTests(unittest.TestCase):
    def test_safe_getattr_reads_existing_attribute(self):
        obj = FakeDriver(title="标题")

        self.assertEqual(safe_getattr(obj, "title"), "标题")

    def test_safe_getattr_returns_default_when_attribute_raises(self):
        self.assertEqual(safe_getattr(BrokenAttr(), "bad", default="fallback"), "fallback")

    def test_safe_call_missing_method_returns_default(self):
        self.assertEqual(safe_call(FakeMethods(), "missing", default="fallback"), "fallback")
        self.assertEqual(safe_call(FakeMethods(), "hello", "fallback", "world"), "hello world")
        self.assertEqual(safe_call(FakeMethods(), "explode", default="fallback"), "fallback")

    def test_safe_string_truncates_long_text(self):
        self.assertEqual(safe_string("  abcdef  ", limit=3), "abc")
        self.assertEqual(safe_string(None), "")

    def test_html_to_digest_removes_simple_tags_and_keeps_chinese(self):
        digest = html_to_digest("<html><body><h1>课程页面</h1><p>继续学习</p></body></html>")

        self.assertIn("课程页面", digest)
        self.assertIn("继续学习", digest)
        self.assertNotIn("<h1>", digest)

    def test_extract_basic_driver_info_reads_fake_driver(self):
        driver = FakeDriver(
            url="https://example.com/course",
            title="国家安全教育",
            page_source="<div>课程目录 <b>第一章</b></div>",
        )

        info = extract_basic_driver_info(driver)

        self.assertEqual(info["url"], "https://example.com/course")
        self.assertEqual(info["title"], "国家安全教育")
        self.assertIn("课程目录", info["page_text_digest"])

    def test_extract_basic_driver_info_handles_none_driver(self):
        info = extract_basic_driver_info(None)

        self.assertEqual(info["url"], "")
        self.assertEqual(info["title"], "")
        self.assertEqual(info["page_text_digest"], "")

    def test_normalize_video_state_handles_dict(self):
        state = normalize_video_state({"present": True, "duration": 60, "current_time": 58, "paused": True})

        self.assertTrue(state["present"])
        self.assertEqual(state["duration"], 60.0)
        self.assertTrue(state["completed"])

    def test_normalize_video_state_handles_object(self):
        state = normalize_video_state(VideoObject())

        self.assertTrue(state["present"])
        self.assertTrue(state["playing"])
        self.assertFalse(state["completed"])

    def test_normalize_video_state_handles_none(self):
        state = normalize_video_state(None)

        self.assertFalse(state["present"])
        self.assertTrue(state["paused"])
        self.assertFalse(state["completed"])

    def test_normalize_dialogs_handles_list_of_dicts(self):
        dialogs = normalize_dialogs([{"text": "验证码弹窗", "role": "dialog", "visible": True}])

        self.assertEqual(dialogs[0]["text"], "验证码弹窗")
        self.assertEqual(dialogs[0]["role"], "dialog")
        self.assertTrue(dialogs[0]["visible"])

    def test_normalize_dialogs_limits_max_dialogs(self):
        dialogs = normalize_dialogs([{"text": str(i)} for i in range(5)], max_dialogs=2)

        self.assertEqual(len(dialogs), 2)

    def test_normalize_dialogs_handles_objects(self):
        dialogs = normalize_dialogs(DialogObject())

        self.assertEqual(dialogs[0]["role"], "dialog")
        self.assertIn("判断题", dialogs[0]["text"])

    def test_infer_state_detects_video_page(self):
        state = infer_state_from_digest(
            "https://example.com/study",
            "视频",
            "课程页面",
            video_state={"present": True, "paused": False},
        )

        self.assertEqual(state.primary_state, "video_page")
        self.assertTrue(state.flags["has_video"])

    def test_infer_state_detects_captcha_overlay(self):
        state = infer_state_from_digest("", "登录", "请输入密码 验证码")

        self.assertEqual(state.primary_state, "login")
        self.assertIn("captcha", state.overlays)
        self.assertTrue(state.flags["has_captcha"])

    def test_infer_state_detects_course_markers(self):
        state = infer_state_from_digest("", "课程", "课程目录 第一章 继续学习")

        self.assertEqual(state.primary_state, "course_catalog")
        self.assertTrue(state.flags["has_course_markers"])

    def test_observe_returns_observation_frame(self):
        observer = AgentObserver()
        frame = observer.observe(
            FakeDriver(page_source="<html>课程目录 章节</html>"),
            mode="video",
            course_name="国家安全教育",
            video_state={"present": True, "paused": False},
            dialogs=[{"text": "普通弹窗"}],
            notes="中文备注",
        )

        self.assertIsInstance(frame, ObservationFrame)
        self.assertEqual(frame.mode, "video")
        self.assertEqual(frame.course_name, "国家安全教育")
        self.assertEqual(frame.state.primary_state, "video_page")
        self.assertEqual(frame.dialogs[0]["text"], "普通弹窗")

    def test_observe_prefers_external_state(self):
        external = StateSnapshot(primary_state="error", reason="external")
        frame = AgentObserver().observe(FakeDriver(), state=external)

        self.assertEqual(frame.state.primary_state, "error")
        self.assertEqual(frame.state.reason, "external")

    def test_observe_to_event_returns_agent_event(self):
        frame = AgentObserver().observe(FakeDriver(), mode="video", notes="observe only")
        event = observe_to_event(frame, run_id="run-1", step_index=7, account_file="account.json")

        self.assertIsInstance(event, AgentEvent)
        self.assertEqual(event.run_id, "run-1")
        self.assertEqual(event.step_index, 7)
        self.assertEqual(event.observation.url, frame.url)
        self.assertEqual(event.notes, "observe only")

    def test_chinese_url_title_notes_survive_json(self):
        frame = AgentObserver().observe(
            FakeDriver(url="https://example.com/课程", title="课程标题", page_source="<p>继续学习</p>"),
            notes="中文备注",
        )
        event = observe_to_event(frame, run_id="run-cn")
        data = json.loads(event.to_json_line())

        self.assertEqual(data["observation"]["title"], "课程标题")
        self.assertEqual(data["notes"], "中文备注")
        self.assertNotIn("\\u4e2d", event.to_json_line())

    def test_observe_does_not_write_runtime_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            before = set(Path(tmp).rglob("*"))
            AgentObserver(ObserverOptions()).observe(FakeDriver(url=f"{tmp}/课程"))
            after = set(Path(tmp).rglob("*"))

            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()

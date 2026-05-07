import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from agent.schemas import (  # noqa: E402
    ActionProposal,
    AgentEvent,
    ObservationFrame,
    StateSnapshot,
    clamp_confidence,
    json_dumps_line,
    safe_dict,
    safe_list,
)


class AgentSchemasTests(unittest.TestCase):
    def test_state_snapshot_instantiates(self):
        snapshot = StateSnapshot(
            primary_state="video_page",
            overlays=["quiz_popup"],
            flags={"has_video": True},
            task_phase="watch_video",
            confidence=0.7,
            reason="video visible",
        )

        self.assertEqual(snapshot.primary_state, "video_page")
        self.assertEqual(snapshot.overlays, ["quiz_popup"])
        self.assertTrue(snapshot.flags["has_video"])
        self.assertEqual(snapshot.confidence, 0.7)

    def test_state_snapshot_round_trip_is_stable(self):
        snapshot = StateSnapshot(
            primary_state="course_catalog",
            overlays=["loading"],
            flags={"has_course_markers": True},
            task_phase="navigate_course",
            confidence=1.5,
            reason="catalog markers found",
        )

        restored = StateSnapshot.from_dict(snapshot.to_dict())

        self.assertEqual(restored.to_dict(), snapshot.to_dict())
        self.assertEqual(restored.confidence, 1.0)

    def test_observation_frame_minimal(self):
        frame = ObservationFrame.minimal(
            url="https://example.test/study",
            title="课程页面",
            mode="video",
            course_name="国家安全教育",
        )

        self.assertEqual(frame.url, "https://example.test/study")
        self.assertEqual(frame.title, "课程页面")
        self.assertIsInstance(frame.state, StateSnapshot)
        self.assertTrue(frame.timestamp)

    def test_observation_frame_serializes_reserved_fields(self):
        frame = ObservationFrame(
            video_state={"present": True, "current_time": 12.5},
            dialogs=[{"type": "quiz_popup", "text": "AI随堂练习"}],
            elements_digest=[{"id": 1, "text": "播放"}],
            screenshot_path="runtime/screenshot.png",
            html_snapshot_path="runtime/page.html",
            som_image_path="runtime/som.png",
        )

        data = frame.to_dict()
        restored = ObservationFrame.from_dict(data)

        self.assertEqual(restored.video_state["current_time"], 12.5)
        self.assertEqual(restored.dialogs[0]["type"], "quiz_popup")
        self.assertEqual(restored.elements_digest[0]["text"], "播放")
        json.dumps(restored.to_dict(), ensure_ascii=False)

    def test_action_proposal_noop_does_not_execute(self):
        proposal = ActionProposal.noop(reason="observe only")

        self.assertEqual(proposal.action_type, "noop")
        self.assertFalse(proposal.approved)
        self.assertEqual(proposal.reason, "observe only")
        self.assertNotIn("webelement", str(proposal.to_dict()).lower())

    def test_action_proposal_confidence_is_clamped(self):
        high = ActionProposal(confidence=3.0)
        low = ActionProposal(confidence=-2.0)
        invalid = ActionProposal(confidence="bad")

        self.assertEqual(high.confidence, 1.0)
        self.assertEqual(low.confidence, 0.0)
        self.assertEqual(invalid.confidence, 0.0)
        self.assertEqual(clamp_confidence(0.4), 0.4)

    def test_agent_event_outputs_valid_json_line(self):
        event = AgentEvent(
            event_type="observe",
            run_id="run-1",
            step_index=3,
            mode="video",
            state=StateSnapshot(primary_state="video_page"),
            observation=ObservationFrame.minimal(url="https://example.test"),
            proposal=ActionProposal.noop("wait for next frame"),
            notes="中文备注",
        )

        line = event.to_json_line()
        data = json.loads(line)

        self.assertTrue(line.endswith("\n"))
        self.assertEqual(data["event_type"], "observe")
        self.assertEqual(data["state"]["primary_state"], "video_page")
        self.assertEqual(data["proposal"]["action_type"], "noop")

    def test_agent_event_from_json_line_restores_event(self):
        original = AgentEvent(
            event_type="proposal",
            run_id="run-2",
            step_index=5,
            proposal=ActionProposal(source="rule_engine", action_type="observe_again", confidence=0.8),
        )

        restored = AgentEvent.from_json_line(original.to_json_line())

        self.assertEqual(restored.event_type, "proposal")
        self.assertEqual(restored.run_id, "run-2")
        self.assertIsInstance(restored.proposal, ActionProposal)
        self.assertEqual(restored.proposal.action_type, "observe_again")

    def test_missing_fields_do_not_crash(self):
        state = StateSnapshot.from_dict({})
        frame = ObservationFrame.from_dict({"state": {}})
        proposal = ActionProposal.from_dict({})
        event = AgentEvent.from_dict({"observation": {}, "proposal": {}, "state": {}})
        invalid_json_event = AgentEvent.from_json_line("not json")

        self.assertEqual(state.primary_state, "unknown")
        self.assertIsInstance(frame.state, StateSnapshot)
        self.assertEqual(proposal.action_type, "noop")
        self.assertIsInstance(event.observation, ObservationFrame)
        self.assertEqual(invalid_json_event.event_type, "observe")

    def test_json_output_keeps_chinese_unescaped(self):
        line = json_dumps_line({"notes": "中文内容", "state": {"primary_state": "视频页面"}})

        self.assertIn("中文内容", line)
        self.assertNotIn("\\u4e2d", line)
        self.assertEqual(json.loads(line)["notes"], "中文内容")

    def test_safe_helpers_degrade_gently(self):
        self.assertEqual(safe_dict(None), {})
        self.assertEqual(safe_dict(["bad"]), {})
        self.assertEqual(safe_list(None), [])
        self.assertEqual(safe_list("abc"), [])
        self.assertEqual(safe_list(("a", "b")), ["a", "b"])


if __name__ == "__main__":
    unittest.main()

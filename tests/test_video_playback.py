import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from video_playback import (  # noqa: E402
    VideoState,
    get_video_duration,
    get_video_progress,
    get_video_state,
    is_video_completed,
    is_video_playing,
)


class FakeDriver:
    def __init__(self, payload):
        self.payload = payload

    def execute_script(self, script):
        return self.payload


class VideoPlaybackTests(unittest.TestCase):
    def test_video_state_parses_payload(self):
        driver = FakeDriver({
            "present": True,
            "duration": 120,
            "currentTime": 30,
            "paused": False,
            "ended": False,
        })

        state = get_video_state(driver)

        self.assertTrue(state.present)
        self.assertEqual(state.duration, 120)
        self.assertEqual(state.current_time, 30)
        self.assertTrue(state.playing)

    def test_missing_video_returns_empty_state(self):
        state = get_video_state(FakeDriver({"present": False}))

        self.assertFalse(state.present)
        self.assertFalse(state.playing)

    def test_completed_when_ended(self):
        driver = FakeDriver({
            "present": True,
            "duration": 120,
            "currentTime": 40,
            "paused": True,
            "ended": True,
        })

        self.assertTrue(is_video_completed(driver))

    def test_completed_when_close_to_end(self):
        state = VideoState(present=True, duration=120, current_time=116, paused=False, ended=False)

        self.assertTrue(state.completed)

    def test_helpers_return_scalar_values(self):
        driver = FakeDriver({
            "present": True,
            "duration": 90,
            "currentTime": 45,
            "paused": False,
            "ended": False,
        })

        self.assertEqual(get_video_duration(driver), 90)
        self.assertEqual(get_video_progress(driver), 45)
        self.assertTrue(is_video_playing(driver))


if __name__ == "__main__":
    unittest.main()

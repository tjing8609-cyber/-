import sys
import unittest
from pathlib import Path

from selenium.webdriver.common.by import By


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from video_playback import (  # noqa: E402
    ProgressStallMonitor,
    VideoState,
    click_visible_play_button,
    get_video_duration,
    get_video_progress,
    get_video_state,
    is_video_completed,
    is_video_playing,
    start_video_playback,
)


class FakeElement:
    def __init__(self, displayed=True):
        self.displayed = displayed
        self.clicked = False

    def click(self):
        self.clicked = True

    def is_displayed(self):
        return self.displayed


class FakeDriver:
    def __init__(self, payload=None, elements=None):
        self.payload = payload
        self.elements = elements or {}

    def execute_script(self, script):
        return self.payload

    def find_element(self, by, value):
        raise RuntimeError("not found")

    def find_elements(self, by, value):
        return self.elements.get((by, value), [])


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

    def test_progress_monitor_requests_recover_after_stalls(self):
        monitor = ProgressStallMonitor(recover_after=3)

        self.assertFalse(monitor.update(10).stalled)
        self.assertFalse(monitor.update(10.5).should_recover)
        self.assertFalse(monitor.update(10.7).should_recover)
        decision = monitor.update(10.8)

        self.assertTrue(decision.stalled)
        self.assertTrue(decision.should_recover)

    def test_progress_monitor_does_not_recover_near_end(self):
        monitor = ProgressStallMonitor(recover_after=2, near_end_percent=95)
        monitor.update(100)
        monitor.update(100, progress_percent=96)
        decision = monitor.update(100, progress_percent=96)

        self.assertTrue(decision.stalled)
        self.assertFalse(decision.should_recover)

    def test_progress_monitor_reports_recovered_progress(self):
        monitor = ProgressStallMonitor(recover_after=3)
        monitor.update(5)
        monitor.update(5)
        decision = monitor.update(8)

        self.assertTrue(decision.recovered)
        self.assertEqual(decision.stall_count, 0)

    def test_click_visible_play_button(self):
        button = FakeElement()
        driver = FakeDriver(elements={
            (By.XPATH, "//button[contains(@class, 'play-btn')]"): [button]
        })

        self.assertTrue(click_visible_play_button(driver))
        self.assertTrue(button.clicked)

    def test_start_video_playback_uses_play_button_fallback(self):
        button = FakeElement()
        driver = FakeDriver(elements={
            (By.XPATH, "//button[contains(@class, 'play-btn')]"): [button]
        })

        self.assertTrue(start_video_playback(driver, wait_func=lambda _seconds: None))
        self.assertTrue(button.clicked)


if __name__ == "__main__":
    unittest.main()

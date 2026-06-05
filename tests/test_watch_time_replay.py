import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from watch_time_replay import is_replay_watched_enabled, run_replay_loop  # noqa: E402


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def warning(self, message):
        self.messages.append(("warning", message))

    def error(self, message):
        self.messages.append(("error", message))

    def debug(self, message):
        self.messages.append(("debug", message))


class FakeDriver:
    def __init__(self, video_infos):
        self.video_infos = list(video_infos)

    def execute_script(self, script):
        if self.video_infos:
            return self.video_infos.pop(0)
        return {"present": True, "duration": 10, "currentTime": 10, "ended": True}


class FakePlayer:
    def __init__(self):
        self.logger = FakeLogger()
        self.max_watch_minutes = 0.3
        self.total_watch_time_seconds = 0.0
        self.progress_values = [0, 10, 0, 10]
        self.driver = FakeDriver(
            [
                {"present": True, "duration": 10, "currentTime": 10, "ended": True},
                {"present": True, "duration": 10, "currentTime": 10, "ended": True},
            ]
        )
        self.limit_logs = []
        self.ensure_calls = 0

    def get_video_progress(self):
        if self.progress_values:
            return self.progress_values.pop(0)
        return 10

    def get_current_video_played_seconds(self, current_video_progress=0, video_start_progress=0):
        return max(0.0, float(current_video_progress or 0) - float(video_start_progress or 0))

    def update_current_video_played_seconds(
        self,
        current_video_played_seconds=0,
        current_video_progress=0,
        last_counted_video_progress=0,
    ):
        played = float(current_video_played_seconds or 0)
        current = float(current_video_progress or 0)
        last = float(last_counted_video_progress or 0)
        if current >= last:
            played += current - last
        return played, current

    def get_session_watch_seconds(
        self,
        current_video_progress=0,
        video_start_total_time=None,
        video_start_progress=0,
        current_video_played_seconds=None,
    ):
        base = self.total_watch_time_seconds if video_start_total_time is None else video_start_total_time
        if current_video_played_seconds is None:
            current_video_played_seconds = self.get_current_video_played_seconds(
                current_video_progress,
                video_start_progress,
            )
        return float(base or 0) + float(current_video_played_seconds or 0)

    def commit_current_video_watch_time(
        self,
        current_video_progress=0,
        video_start_total_time=None,
        video_start_progress=0,
        current_video_played_seconds=None,
    ):
        self.total_watch_time_seconds = max(
            self.total_watch_time_seconds,
            self.get_session_watch_seconds(
                current_video_progress,
                video_start_total_time,
                video_start_progress,
                current_video_played_seconds,
            ),
        )
        return self.total_watch_time_seconds

    def has_reached_max_watch_time(
        self,
        current_video_progress=0,
        video_start_total_time=None,
        video_start_progress=0,
        current_video_played_seconds=None,
    ):
        return (
            self.get_session_watch_seconds(
                current_video_progress,
                video_start_total_time,
                video_start_progress,
                current_video_played_seconds,
            )
            >= self.max_watch_minutes * 60
        )

    def format_watch_time_text(self, total_watch_seconds):
        return f"{float(total_watch_seconds or 0):.0f}s"

    def log_max_watch_time_reached(self, videos_played=0):
        self.limit_logs.append(videos_played)

    def is_video_playing(self):
        return True

    def ensure_video_playing(self):
        self.ensure_calls += 1
        return True

    def smart_wait(self, seconds):
        return None


class WatchTimeReplayTests(unittest.TestCase):
    def test_string_config_enables_replay_mode(self):
        self.assertTrue(is_replay_watched_enabled({"replay_watched_videos": "true"}))
        self.assertTrue(is_replay_watched_enabled({"replay_watched_videos": "1"}))
        self.assertFalse(is_replay_watched_enabled({"replay_watched_videos": "false"}))

    def test_replay_loop_clicks_replay_and_stops_at_time_limit(self):
        player = FakePlayer()
        replay_clicks = []

        result = run_replay_loop(
            player,
            click_replay=lambda: replay_clicks.append("clicked") or True,
            sleep_func=lambda _seconds: None,
            check_interval_seconds=1,
        )

        self.assertTrue(result.reached_limit)
        self.assertEqual(result.reason, "time_limit")
        self.assertEqual(result.loops_completed, 1)
        self.assertEqual(replay_clicks, ["clicked"])
        self.assertEqual(player.total_watch_time_seconds, 20)
        self.assertEqual(player.limit_logs, [1])


if __name__ == "__main__":
    unittest.main()

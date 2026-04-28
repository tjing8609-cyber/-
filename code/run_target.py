from dataclasses import dataclass, field


@dataclass(frozen=True)
class RunTarget:
    detect_message: str
    module_name: str
    class_name: str
    start_message: str
    import_error_message: str
    missing_file_message: str
    extra_messages: tuple = field(default_factory=tuple)
    type_message: str = None

    def as_legacy_dict(self):
        return {
            "detect_message": self.detect_message,
            "extra_messages": list(self.extra_messages),
            "type_message": self.type_message,
            "module_name": self.module_name,
            "class_name": self.class_name,
            "start_message": self.start_message,
            "import_error_message": self.import_error_message,
            "missing_file_message": self.missing_file_message,
        }


def _course_type_value(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _mode_and_type(mode_or_context, course_type):
    if hasattr(mode_or_context, "mode") and hasattr(mode_or_context, "course_type"):
        return mode_or_context.mode, mode_or_context.course_type
    return mode_or_context, course_type


def resolve_run_target(mode_or_context, course_type=None):
    mode, course_type = _mode_and_type(mode_or_context, course_type)
    course_type = _course_type_value(course_type)

    if mode == "quiz_only" or course_type == 3:
        extra_messages = ()
        if course_type == 3 and mode != "quiz_only":
            extra_messages = ("[提示] 建议使用 mode='quiz_only' 代替 course_type=3",)
        return RunTarget(
            detect_message="[检测] 纯答题模式",
            extra_messages=extra_messages,
            type_message=None,
            module_name="zhidao_quiz_only_player",
            class_name="ZhidaoQuizOnlyPlayer",
            start_message="[启动] zhidao_quiz_only_player.py",
            import_error_message="[错误] 无法导入纯答题播放器: {error}",
            missing_file_message="请确保 zhidao_quiz_only_player.py 文件存在",
        )

    video_targets = {
        1: RunTarget(
            detect_message="[检测] 无题目课程",
            module_name="zhidao_web_auto_player_final",
            class_name="ZhidaoWebAutoPlayerFinal",
            start_message="[启动] zhidao_web_auto_player_final.py",
            import_error_message="[错误] 无法导入旧版播放器: {error}",
            missing_file_message="请确保 zhidao_web_auto_player_final.py 文件存在",
            type_message="[类型] 1",
        ),
        2: RunTarget(
            detect_message="[检测] 有题目课程",
            module_name="zhidao_web_auto_player_with_quiz",
            class_name="ZhidaoWebAutoPlayerWithQuiz",
            start_message="[启动] zhidao_web_auto_player_with_quiz.py",
            import_error_message="[错误] 无法导入新版播放器: {error}",
            missing_file_message="请确保 zhidao_web_auto_player_with_quiz.py 文件存在",
            type_message="[类型] 2",
        ),
    }

    if mode == "video" and course_type in video_targets:
        return video_targets[course_type]
    return None


__all__ = ["RunTarget", "resolve_run_target"]

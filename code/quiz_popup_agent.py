from dataclasses import dataclass
from typing import Callable, List


@dataclass
class QuizPopupToolbox:
    check_for_quiz: Callable[[], bool]
    scroll_dialog: Callable[[str], bool]
    extract_visible_answers: Callable[[], List[str]]
    get_options: Callable[[], list]
    is_multi_choice: Callable[[], bool]
    select_options: Callable[[List[str]], bool]
    click_single_option: Callable[[str, list], bool]
    submit: Callable[[], bool]
    close: Callable[[], bool]
    answer_with_api: Callable[[list], List[str]]
    wait: Callable[[float], None]


def _log(logger, level, message):
    if logger is None:
        return
    getattr(logger, level)(message)


def _safe_call(callback, default=None):
    try:
        return callback()
    except Exception:
        return default


def run_quiz_popup_agent(agent, toolbox, logger=None):
    """Run the video popup quiz agent with explicit UI/API tools.

    The agent policy decides whether to select, submit, and close. The toolbox
    supplies the concrete browser actions and DeepSeek-backed answering hook.
    """
    if not toolbox.check_for_quiz():
        return False

    toolbox.scroll_dialog("bottom")
    letters = _safe_call(toolbox.extract_visible_answers, default=[]) or []
    if not letters:
        toolbox.scroll_dialog("bottom")
        letters = _safe_call(toolbox.extract_visible_answers, default=[]) or []

    options = _safe_call(toolbox.get_options, default=[]) or []
    if not options:
        _log(logger, "info", "🔔 未检测到选项，请手动处理；程序继续监控")
        return False

    source = "visible_answer"
    if not letters:
        api_letters = _safe_call(lambda: toolbox.answer_with_api(options), default=[]) or []
        if api_letters:
            letters = api_letters
            source = "api_popup"

    decision = agent.decide(
        letters=letters,
        option_count=len(options),
        source=source,
    )
    if decision.letters:
        _log(logger, "info", f"🤖 Agent建议答案: {', '.join(decision.letters)} ({decision.reason})")
    if not decision.should_select:
        _log(logger, "info", f"🔔 当前模式不自动点击选项: {decision.reason}")
        return False

    if toolbox.is_multi_choice():
        toolbox.select_options(decision.letters)
    else:
        toolbox.click_single_option(decision.letters[0], options)
        toolbox.scroll_dialog("bottom")

    if decision.should_submit:
        toolbox.wait(1)
        toolbox.submit()

    if decision.should_close:
        toolbox.wait(2)
        toolbox.close()

    return True


__all__ = [
    "QuizPopupToolbox",
    "run_quiz_popup_agent",
]

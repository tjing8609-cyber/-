from dataclasses import dataclass
from pathlib import Path

from config_loader import ConfigLoadError, load_json_config


VALID_MODES = ("video", "quiz_only")
DEFAULT_MODE = "video"
DEFAULT_COURSE_TYPE = 1
DEFAULT_COURSE_NAME = "未指定"
DEFAULT_QUIZ_TYPE = "课程测试"


@dataclass(frozen=True)
class RunContext:
    project_root: Path
    code_dir: Path
    account_file: str
    account_path: Path
    config: dict
    mode: str
    course_type: object
    course_name: str
    quiz_type: str
    headless: bool = False

    @property
    def runtime_dir(self):
        return self.project_root / "runtime"

    @property
    def log_dir(self):
        return self.project_root / "log"

    @property
    def launch_dir(self):
        return self.project_root / "启动"

    @property
    def normalized_config(self):
        data = dict(self.config)
        data["mode"] = self.mode
        data["course_type"] = self.course_type
        data["course_name"] = self.course_name
        data["quiz_type"] = self.quiz_type
        return data


def normalize_mode(value, default=DEFAULT_MODE):
    mode = str(value or default).strip()
    return mode or default


def normalize_course_type(value, default=DEFAULT_COURSE_TYPE):
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def normalize_text(value, default=""):
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def resolve_project_root(code_dir=None):
    if code_dir is None:
        code_path = Path(__file__).resolve().parent
    else:
        code_path = Path(code_dir).resolve()
    return code_path.parent, code_path


def account_path_candidates(account_file, project_root, code_dir):
    raw_path = Path(account_file).expanduser()
    if raw_path.is_absolute():
        return [raw_path]

    candidates = [
        Path.cwd() / raw_path,
        project_root / raw_path,
        code_dir / raw_path,
        project_root / "启动" / raw_path,
    ]
    seen = set()
    unique = []
    for candidate in candidates:
        resolved_key = str(candidate.resolve(strict=False)).lower()
        if resolved_key not in seen:
            seen.add(resolved_key)
            unique.append(candidate)
    return unique


def resolve_account_path(account_file, project_root, code_dir):
    candidates = account_path_candidates(account_file, project_root, code_dir)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve(strict=False)


def create_run_context(account_file, headless=False, code_dir=None, account_config=None):
    project_root, code_path = resolve_project_root(code_dir)
    account_path = resolve_account_path(account_file, project_root, code_path)
    config = dict(account_config) if account_config is not None else load_json_config(account_path)

    mode = normalize_mode(config.get("mode", DEFAULT_MODE))
    course_type = normalize_course_type(config.get("course_type", DEFAULT_COURSE_TYPE))
    course_name = normalize_text(config.get("course_name"), DEFAULT_COURSE_NAME)
    quiz_type = normalize_text(config.get("quiz_type"), DEFAULT_QUIZ_TYPE)

    return RunContext(
        project_root=project_root,
        code_dir=code_path,
        account_file=str(account_file),
        account_path=account_path,
        config=config,
        mode=mode,
        course_type=course_type,
        course_name=course_name,
        quiz_type=quiz_type,
        headless=bool(headless),
    )


__all__ = [
    "ConfigLoadError",
    "RunContext",
    "create_run_context",
    "normalize_course_type",
    "normalize_mode",
    "resolve_account_path",
]

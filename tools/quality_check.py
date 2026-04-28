import json
import py_compile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PY_FILES = [
    ROOT / "auto_start.py",
    ROOT / "code" / "zhidao_launcher.py",
    ROOT / "code" / "runtime_center.py",
    ROOT / "code" / "course_outline.py",
    ROOT / "code" / "page_detection.py",
    ROOT / "code" / "quiz_answering.py",
    ROOT / "code" / "task_orchestrator.py",
    ROOT / "code" / "zhidao_quiz_only_player.py",
    ROOT / "code" / "zhidao_web_auto_player_final.py",
    ROOT / "code" / "zhidao_web_auto_player_with_quiz.py",
    ROOT / "tools" / "selector_profile_switch.py",
    ROOT / "tools" / "runtime_control.py",
    ROOT / "tools" / "run_tests.py",
]
JSON_FILES = [
    ROOT / "启动" / "account.json.template",
    ROOT / "启动" / "selectors.default.json",
    ROOT / "启动" / "selectors.active.json",
    ROOT / "启动" / "selectors_versions" / "v1.json",
]


def compile_python_files():
    for file_path in PY_FILES:
        py_compile.compile(str(file_path), doraise=True)
        print(f"[OK] py_compile: {file_path.relative_to(ROOT)}")


def validate_json_files():
    for file_path in JSON_FILES:
        with file_path.open("r", encoding="utf-8") as f:
            json.load(f)
        print(f"[OK] json: {file_path.relative_to(ROOT)}")


def main():
    compile_python_files()
    validate_json_files()
    print("[DONE] quality_check passed")


if __name__ == "__main__":
    main()

import json
import py_compile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PY_FILES = [
    ROOT / "auto_start.py",
    ROOT / "code" / "zhidao_launcher.py",
    ROOT / "code" / "zhidao_quiz_only_player.py",
    ROOT / "code" / "zhidao_web_auto_player_final.py",
    ROOT / "code" / "zhidao_web_auto_player_with_quiz.py",
]
JSON_FILES = [
    ROOT / "启动" / "account.json.template",
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

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="运行控制：暂停/恢复/停止")
    parser.add_argument("--paused", choices=["true", "false"], default=None)
    parser.add_argument("--stop", choices=["true", "false"], default=None)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    runtime_dir = project_root / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    control_file = runtime_dir / "control.json"

    data = {"paused": False, "stop": False}
    if control_file.exists():
        data = json.loads(control_file.read_text(encoding="utf-8"))

    if args.paused is not None:
        data["paused"] = args.paused == "true"
    if args.stop is not None:
        data["stop"] = args.stop == "true"

    control_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] control updated: {control_file}")
    print(json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    main()

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_step(name, command):
    print(f"[RUN] {name}: {' '.join(command)}")
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        print(f"[FAIL] {name}: exit={result.returncode}")
        return result.returncode
    print(f"[OK] {name}")
    return 0


def main():
    steps = [
        ("quality_check", [sys.executable, str(ROOT / "tools" / "quality_check.py")]),
        ("unit_tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests"]),
    ]
    for name, command in steps:
        code = run_step(name, command)
        if code != 0:
            return code
    print("[DONE] all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

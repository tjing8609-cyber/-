import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="切换选择器配置版本")
    parser.add_argument("--profile", required=True, help="版本名，如 v1")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    source = project_root / "启动" / "selectors_versions" / f"{args.profile}.json"
    target = project_root / "启动" / "selectors.active.json"

    if not source.exists():
        raise FileNotFoundError(f"未找到配置版本: {source}")

    data = json.loads(source.read_text(encoding="utf-8"))
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] switched selector profile to {args.profile}")


if __name__ == "__main__":
    main()

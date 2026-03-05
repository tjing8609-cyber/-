import importlib.util
import json
import os
import traceback
from datetime import datetime


def ensure_runtime_dir(project_root):
    runtime_dir = os.path.join(project_root, "runtime")
    os.makedirs(runtime_dir, exist_ok=True)
    return runtime_dir


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_health_check(config, account_file, project_root):
    checks = []
    warnings = []
    errors = []

    username = (config.get("username") or "").strip()
    password = (config.get("password") or "").strip()
    course_name = (config.get("course_name") or "").strip()
    course_url = (config.get("course_url") or "").strip()
    mode = config.get("mode", "video")
    course_type = config.get("course_type", 1)
    api_key = (config.get("deepseek_api_key") or "").strip()

    checks.append({"name": "username", "ok": bool(username)})
    checks.append({"name": "password", "ok": bool(password)})
    checks.append({"name": "course_locator", "ok": bool(course_name or course_url)})
    checks.append({"name": "mode", "ok": mode in ["video", "quiz_only"]})
    checks.append({"name": "course_type", "ok": course_type in [1, 2, 3]})
    checks.append({"name": "quiz_mode_api", "ok": not (mode == "quiz_only" and not api_key)})

    valid_combo = (mode == "quiz_only") or (mode == "video" and course_type in [1, 2]) or (course_type == 3)
    checks.append({"name": "mode_course_type_combo", "ok": valid_combo})

    if course_type == 3 and mode != "quiz_only":
        warnings.append("course_type=3 建议配合 mode='quiz_only'")
    if not course_name and course_url:
        warnings.append("使用 course_url 直达课程，已跳过课程名定位")

    deps = ["selenium", "webdriver_manager", "openai", "tenacity"]
    for dep in deps:
        dep_ok = importlib.util.find_spec(dep) is not None
        checks.append({"name": f"dependency:{dep}", "ok": dep_ok})
        if not dep_ok:
            errors.append(f"缺少依赖: {dep}")

    for item in checks:
        if not item["ok"]:
            if item["name"].startswith("dependency:"):
                continue
            errors.append(f"检查失败: {item['name']}")

    report = {
        "timestamp": _now(),
        "account_file": account_file,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "ok": len(errors) == 0
    }

    runtime_dir = ensure_runtime_dir(project_root)
    report_file = os.path.join(runtime_dir, "health_report_latest.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report, report_file


def load_selectors(project_root):
    base_dir = os.path.join(project_root, "启动")
    default_file = os.path.join(base_dir, "selectors.default.json")
    active_file = os.path.join(base_dir, "selectors.active.json")

    default_selectors = {}
    active_selectors = {}

    if os.path.exists(default_file):
        with open(default_file, "r", encoding="utf-8") as f:
            default_selectors = json.load(f)

    if os.path.exists(active_file):
        try:
            with open(active_file, "r", encoding="utf-8") as f:
                active_selectors = json.load(f)
        except Exception:
            active_selectors = {}

    merged = dict(default_selectors)
    merged.update(active_selectors)
    return merged


def selector_value(selectors, key, default=None):
    return selectors.get(key, default)


def update_observability(project_root, payload):
    runtime_dir = ensure_runtime_dir(project_root)
    state_file = os.path.join(runtime_dir, "observability.json")
    data = {"timestamp": _now()}
    data.update(payload)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return state_file


def read_control_flags(project_root):
    runtime_dir = ensure_runtime_dir(project_root)
    control_file = os.path.join(runtime_dir, "control.json")
    if not os.path.exists(control_file):
        return {"paused": False, "stop": False}, control_file
    try:
        with open(control_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"paused": bool(data.get("paused", False)), "stop": bool(data.get("stop", False))}, control_file
    except Exception:
        return {"paused": False, "stop": False}, control_file


def write_failure_snapshot(project_root, account_file, module_name, player, error):
    runtime_dir = ensure_runtime_dir(project_root)
    failure_dir = os.path.join(runtime_dir, "failure_snapshots")
    os.makedirs(failure_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    case_dir = os.path.join(failure_dir, f"{stamp}_{os.path.basename(account_file).replace('.json', '')}")
    os.makedirs(case_dir, exist_ok=True)

    snapshot = {
        "timestamp": _now(),
        "account_file": account_file,
        "module_name": module_name,
        "error": str(error),
        "traceback": traceback.format_exc()
    }

    try:
        driver = getattr(player, "driver", None)
        if driver is not None:
            screenshot_file = os.path.join(case_dir, "page.png")
            html_file = os.path.join(case_dir, "page.html")
            driver.save_screenshot(screenshot_file)
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(driver.page_source or "")
            snapshot["screenshot"] = screenshot_file
            snapshot["html"] = html_file
    except Exception as e:
        snapshot["snapshot_error"] = str(e)

    detail_file = os.path.join(case_dir, "snapshot.json")
    with open(detail_file, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    return detail_file

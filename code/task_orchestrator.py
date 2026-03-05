import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from runtime_center import read_control_flags, update_observability


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_accounts(args):
    accounts = []
    if args.accounts:
        accounts.extend([item.strip() for item in args.accounts.split(",") if item.strip()])
    if args.accounts_file:
        with open(args.accounts_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            accounts.extend(data)
        else:
            accounts.extend(data.get("accounts", []))
    if not accounts:
        accounts.append(args.default_account)
    return accounts


def wait_if_paused(project_root):
    while True:
        flags, _ = read_control_flags(project_root)
        if flags.get("stop"):
            return False
        if not flags.get("paused"):
            return True
        print(f"[{now()}] [PAUSE] 调度暂停中，等待恢复...")
        time.sleep(2)


def run_single_task(project_root, account, headless, retry, health_check):
    launcher = os.path.join(project_root, "code", "zhidao_launcher.py")
    cmd = [sys.executable, launcher, "--account", account]
    if headless:
        cmd.append("--headless")
    if not health_check:
        cmd.append("--skip-health-check")

    attempts = retry + 1
    for i in range(1, attempts + 1):
        if not wait_if_paused(project_root):
            return {"account": account, "status": "stopped", "attempt": i, "code": -2}
        print(f"[{now()}] [RUN] {account} attempt={i}/{attempts}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=project_root
        )
        output_tail = []
        for line in process.stdout:
            line = line.rstrip()
            if line:
                print(f"[{os.path.basename(account)}] {line}")
                output_tail.append(line)
                if len(output_tail) > 20:
                    output_tail.pop(0)
        process.wait()
        if process.returncode == 0:
            return {"account": account, "status": "success", "attempt": i, "code": 0}
        if i < attempts:
            print(f"[{now()}] [RETRY] {account} exit={process.returncode}")
            time.sleep(2)
    return {
        "account": account,
        "status": "failed",
        "attempt": attempts,
        "code": process.returncode,
        "tail": output_tail
    }


def main():
    parser = argparse.ArgumentParser(description="多账号任务编排中心")
    parser.add_argument("--accounts", type=str, default="", help="逗号分隔账号配置路径")
    parser.add_argument("--accounts-file", type=str, default="", help="账号列表JSON文件")
    parser.add_argument("--default-account", type=str, default=os.path.join("启动", "account.json"))
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--retry", type=int, default=1)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--disable-health-check", action="store_true")
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    accounts = read_accounts(args)
    print(f"[{now()}] [QUEUE] {len(accounts)} 个任务，最大并发 {args.max_concurrency}")
    update_observability(project_root, {
        "status": "orchestrator_running",
        "queue_size": len(accounts),
        "max_concurrency": args.max_concurrency
    })

    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.max_concurrency)) as executor:
        futures = [
            executor.submit(
                run_single_task,
                project_root,
                account,
                args.headless,
                max(0, args.retry),
                not args.disable_health_check
            )
            for account in accounts
        ]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            done = len(results)
            total = len(accounts)
            success = len([x for x in results if x["status"] == "success"])
            failed = len([x for x in results if x["status"] == "failed"])
            update_observability(project_root, {
                "status": "orchestrator_running",
                "queue_size": total,
                "done": done,
                "success": success,
                "failed": failed,
                "latest": result
            })
            print(f"[{now()}] [PANEL] done={done}/{total} success={success} failed={failed}")

    success = len([x for x in results if x["status"] == "success"])
    failed = len([x for x in results if x["status"] == "failed"])
    stopped = len([x for x in results if x["status"] == "stopped"])
    update_observability(project_root, {
        "status": "orchestrator_completed",
        "queue_size": len(accounts),
        "success": success,
        "failed": failed,
        "stopped": stopped,
        "results": results
    })
    print(f"[{now()}] [DONE] success={success} failed={failed} stopped={stopped}")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

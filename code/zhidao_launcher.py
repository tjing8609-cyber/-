#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Copyright (c) 2025 景潼
Zhidao Auto is licensed under Mulan PSL v2.
You can use this software according to the terms and conditions of the Mulan PSL v2.
You may obtain a copy of Mulan PSL v2 at:
         http://license.coscl.org.cn/MulanPSL2
THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
See the Mulan PSL v2 for more details.

知到网页版自动播放器 - 智能启动器
根据课程类型自动选择对应的播放器版本
"""

import sys
import os
from config_loader import ConfigLoadError
from runtime_center import run_health_check, update_observability, write_failure_snapshot
from player_runner import PlayerImportError, execute_player
from run_context import create_run_context
from run_target import resolve_run_target as resolve_target

# 【修复】设置stdout编码为UTF-8，避免Windows下emoji输出错误
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加code文件夹到Python路径
code_dir = os.path.dirname(os.path.abspath(__file__))
if code_dir not in sys.path:
    sys.path.insert(0, code_dir)


def load_account_config(account_file):
    """加载账号配置。保留旧接口，实际解析逻辑已集中到 run_context/config_loader。"""
    try:
        return create_run_context(account_file, code_dir=code_dir).config
    except ConfigLoadError as e:
        print(f"[错误] {e}")
        sys.exit(1)


def resolve_run_target(mode, course_type):
    """保留旧接口，返回旧版dict结构。"""
    target = resolve_target(mode, course_type)
    return target.as_legacy_dict() if target else None


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='知到网页版自动播放器 - 智能启动器')
    parser.add_argument('--account', type=str, default='account.json', help='账号配置文件（默认: account.json）')
    parser.add_argument('--headless', action='store_true', help='无头模式运行')
    parser.add_argument('--skip-health-check', action='store_true', help='跳过启动前健康检查')
    
    args = parser.parse_args()
    
    try:
        context = create_run_context(args.account, headless=args.headless, code_dir=code_dir)
    except ConfigLoadError as e:
        print(f"[错误] {e}")
        sys.exit(1)

    config = context.normalized_config
    mode = context.mode
    course_type = context.course_type
    course_name = context.course_name
    quiz_type = context.quiz_type
    
    print("=" * 60)
    print("知到网页版自动播放器 - 智能启动器")
    print("=" * 60)
    print(f"[配置] {context.account_path}")
    print(f"[课程] {course_name}")
    print(f"[模式] {mode}")

    project_root = str(context.project_root)
    if not args.skip_health_check:
        report, report_file = run_health_check(config, str(context.account_path), project_root)
        print(f"[健康检查] 报告: {report_file}")
        if report['warnings']:
            for item in report['warnings']:
                print(f"[警告] {item}")
        if not report['ok']:
            for item in report['errors']:
                print(f"[错误] {item}")
            print("[终止] 健康检查未通过")
            sys.exit(1)
    
    run_target = resolve_target(context)
    if run_target is None:
        print(f"[错误] 未知的运行模式: mode={mode}, course_type={course_type}")
        print("运行模式说明:")
        print("  - mode='video' + course_type=1: 无题目视频课程")
        print("  - mode='video' + course_type=2: 有题目视频课程")
        print("  - mode='quiz_only' 或 course_type=3: 纯答题模式")
        sys.exit(1)

    print(run_target.detect_message)
    if run_target.type_message:
        print(run_target.type_message)
    for message in run_target.extra_messages:
        print(message)
    if run_target.module_name == 'zhidao_quiz_only_player':
        print(f"[测试] {quiz_type}")
    print(run_target.start_message)
    print("=" * 60)

    try:
        execute_player(
            run_target,
            context,
            update_observability=update_observability,
            write_failure_snapshot=write_failure_snapshot,
        )
    except PlayerImportError as e:
        print(run_target.import_error_message.format(error=e))
        print(run_target.missing_file_message)
        sys.exit(1)
    except Exception as e:
        raise


if __name__ == '__main__':
    main()

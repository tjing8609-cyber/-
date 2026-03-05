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

import json
import sys
import os
import importlib

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
    """加载账号配置"""
    try:
        # 尝试多种编码
        encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312']
        for encoding in encodings:
            try:
                with open(account_file, 'r', encoding=encoding) as f:
                    return json.load(f)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        # 如果所有编码都失败
        raise Exception("无法解析配置文件")
    except FileNotFoundError:
        print(f"[错误] 找不到配置文件: {account_file}")
        sys.exit(1)
    except Exception as e:
        print(f"[错误] 配置文件错误: {account_file} - {e}")
        sys.exit(1)


def resolve_run_target(mode, course_type):
    if mode == 'quiz_only' or course_type == 3:
        return {
            'detect_message': "[检测] 纯答题模式",
            'extra_messages': ["[提示] 建议使用 mode='quiz_only' 代替 course_type=3"] if course_type == 3 else [],
            'type_message': None,
            'module_name': 'zhidao_quiz_only_player',
            'class_name': 'ZhidaoQuizOnlyPlayer',
            'start_message': "[启动] zhidao_quiz_only_player.py",
            'import_error_message': "[错误] 无法导入纯答题播放器: {error}",
            'missing_file_message': "请确保 zhidao_quiz_only_player.py 文件存在"
        }

    video_targets = {
        1: {
            'detect_message': "[检测] 无题目课程",
            'module_name': 'zhidao_web_auto_player_final',
            'class_name': 'ZhidaoWebAutoPlayerFinal',
            'start_message': "[启动] zhidao_web_auto_player_final.py",
            'import_error_message': "[错误] 无法导入旧版播放器: {error}",
            'missing_file_message': "请确保 zhidao_web_auto_player_final.py 文件存在"
        },
        2: {
            'detect_message': "[检测] 有题目课程",
            'module_name': 'zhidao_web_auto_player_with_quiz',
            'class_name': 'ZhidaoWebAutoPlayerWithQuiz',
            'start_message': "[启动] zhidao_web_auto_player_with_quiz.py",
            'import_error_message': "[错误] 无法导入新版播放器: {error}",
            'missing_file_message': "请确保 zhidao_web_auto_player_with_quiz.py 文件存在"
        }
    }

    if mode == 'video' and course_type in video_targets:
        target = video_targets[course_type].copy()
        target.update({
            'extra_messages': [],
            'type_message': f"[类型] {course_type}"
        })
        return target

    return None


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='知到网页版自动播放器 - 智能启动器')
    parser.add_argument('--account', type=str, default='account.json', help='账号配置文件（默认: account.json）')
    parser.add_argument('--headless', action='store_true', help='无头模式运行')
    
    args = parser.parse_args()
    
    # 加载账号配置
    config = load_account_config(args.account)
    
    # 获取运行模式（新增：优先检查mode字段）
    mode = config.get('mode', 'video')  # 默认为视频模式
    course_type = config.get('course_type', 1)
    course_name = config.get('course_name', '未指定')
    quiz_type = config.get('quiz_type', '课程测试')
    
    print("=" * 60)
    print("知到网页版自动播放器 - 智能启动器")
    print("=" * 60)
    print(f"[配置] {args.account}")
    print(f"[课程] {course_name}")
    print(f"[模式] {mode}")
    
    run_target = resolve_run_target(mode, course_type)
    if run_target is None:
        print(f"[错误] 未知的运行模式: mode={mode}, course_type={course_type}")
        print("运行模式说明:")
        print("  - mode='video' + course_type=1: 无题目视频课程")
        print("  - mode='video' + course_type=2: 有题目视频课程")
        print("  - mode='quiz_only' 或 course_type=3: 纯答题模式")
        sys.exit(1)

    print(run_target['detect_message'])
    if run_target['type_message']:
        print(run_target['type_message'])
    for message in run_target['extra_messages']:
        print(message)
    if run_target['module_name'] == 'zhidao_quiz_only_player':
        print(f"[测试] {quiz_type}")
    print(run_target['start_message'])
    print("=" * 60)

    try:
        module = importlib.import_module(run_target['module_name'])
        player_class = getattr(module, run_target['class_name'])
        player = player_class(account_file=args.account, headless=args.headless)
        player.run()
    except ImportError as e:
        print(run_target['import_error_message'].format(error=e))
        print(run_target['missing_file_message'])
        sys.exit(1)


if __name__ == '__main__':
    main()

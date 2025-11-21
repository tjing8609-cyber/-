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

# 添加code文件夹到Python路径
code_dir = os.path.dirname(os.path.abspath(__file__))
if code_dir not in sys.path:
    sys.path.insert(0, code_dir)


def load_account_config(account_file):
    """加载账号配置"""
    try:
        with open(account_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ 找不到配置文件: {account_file}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"❌ 配置文件格式错误: {account_file}")
        sys.exit(1)


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
    print(f"📁 配置文件: {args.account}")
    print(f"📚 课程名称: {course_name}")
    print(f"🎯 运行模式: {mode}")
    
    # 【新增】优先检查mode字段，向后兼容course_type
    if mode == 'quiz_only':
        # 纯答题模式
        print("📌 检测到: 纯答题模式")
        print(f"📝 测试类型: {quiz_type}")
        print("🚀 启动: zhidao_quiz_only_player.py")
        print("=" * 60)
        
        try:
            from zhidao_quiz_only_player import ZhidaoQuizOnlyPlayer
            
            player = ZhidaoQuizOnlyPlayer(account_file=args.account, headless=args.headless)
            player.run()
            
        except ImportError as e:
            print(f"❌ 无法导入纯答题播放器: {e}")
            print("请确保 zhidao_quiz_only_player.py 文件存在")
            sys.exit(1)
    
    elif mode == 'video' or course_type == 1:
        # 无题目视频模式
        print("📌 检测到: 无题目课程")
        print(f"🎯 课程类型: {course_type}")
        print("🚀 启动: zhidao_web_auto_player_final.py")
        print("=" * 60)
        
        try:
            from zhidao_web_auto_player_final import ZhidaoWebAutoPlayerFinal
            
            player = ZhidaoWebAutoPlayerFinal(account_file=args.account, headless=args.headless)
            player.run()
            
        except ImportError as e:
            print(f"❌ 无法导入旧版播放器: {e}")
            print("请确保 zhidao_web_auto_player_final.py 文件存在")
            sys.exit(1)
    
    elif course_type == 2:
        # 有题目视频模式
        print("📌 检测到: 有题目课程")
        print(f"🎯 课程类型: {course_type}")
        print("🚀 启动: zhidao_web_auto_player_with_quiz.py")
        print("=" * 60)
        
        try:
            from zhidao_web_auto_player_with_quiz import ZhidaoWebAutoPlayerWithQuiz
            
            player = ZhidaoWebAutoPlayerWithQuiz(account_file=args.account, headless=args.headless)
            player.run()
            
        except ImportError as e:
            print(f"❌ 无法导入新版播放器: {e}")
            print("请确保 zhidao_web_auto_player_with_quiz.py 文件存在")
            sys.exit(1)
    
    else:
        print(f"❌ 未知的运行模式: mode={mode}, course_type={course_type}")
        print("运行模式应为: video/quiz_only，课程类型应为 1（无题目）或 2（有题目）")
        sys.exit(1)


if __name__ == '__main__':
    main()

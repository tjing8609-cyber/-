#!/usr/bin/env python3
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

知到网页版自动播放脚本 - 最终版
使用webdriver-manager自动管理Chrome驱动
包含人机验证处理功能
改进版：支持实际视频时长检测、播放状态监控、进度记录、配置文件管理
多实例支持：通过命令行参数指定不同配置文件，实现多账号同时运行
"""

import time
import random
import logging
import json
import os
import sys
import argparse
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from auth_actions import (
    login_method_script as auth_login_method_script,
    login_method_standard as auth_login_method_standard,
    try_login_methods as auth_try_login_methods,
)
from auth_flow import is_login_required, is_login_success, mask_username
from browser_session import create_browser_session, resolve_local_driver_paths
from course_entry import has_course_url, open_course_url
from course_search import find_and_click_course_by_name
from runtime_center import load_selectors, selector_value
from page_detection import (
    close_question_popup as detect_close_question_popup,
    detect_course_layout as detect_course_layout_type,
    is_captcha_present,
    is_course_list_page,
    is_course_page_ready as detect_course_page_ready,
    try_click_enter_study as detect_try_click_enter_study,
    wait_for_captcha_completion as detect_wait_for_captcha_completion,
    wait_for_course_page_ready as detect_wait_for_course_page_ready,
)
from video_playback import (
    click_video_center as playback_click_video_center,
    get_video_duration as playback_get_video_duration,
    get_video_progress as playback_get_video_progress,
    is_video_playing as playback_is_video_playing,
    start_video_playback,
)
from video_catalog import is_catalog_video_completed
from video_discovery import (
    DEFAULT_SIDEBAR_SELECTORS,
    DEFAULT_SIDEBAR_VIDEO_SELECTORS,
    discover_main_area_videos,
    discover_sidebar_videos,
)


class ZhidaoWebAutoPlayerFinal:
    def __init__(self, headless=False, config_file='config.json', account_file='account.json'):
        """初始化浏览器驱动"""
        self.driver = None
        self.wait = None
        self.config_file = config_file
        self.account_file = account_file
        
        # 获取项目根目录（code文件夹的上级目录）
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.selectors = load_selectors(self.project_root)
        
        # 根据账号配置文件名生成独立的进度文件
        # 例如: account1.json -> progress_account1.json
        account_name = os.path.splitext(os.path.basename(account_file))[0]
        self.progress_file = os.path.join(self.project_root, 'log', f'progress_{account_name}.json')
        
        # 设置日志文件名（使用独立的日志文件，存放在log文件夹）
        self.log_file = os.path.join(self.project_root, 'log', f'zhidao_{account_name}.log')
        
        # 初始化刷新计数器（每10次才刷新一次）
        self.items_processed_since_refresh = 0
        self.refresh_interval = 10  # 每10个项目刷新一次
        
        # 初始化累计观看时间（秒）
        self.total_watch_time_seconds = 0
        
        # 【新增】预设观看时间限制（将在load_account时设置）
        self.max_watch_minutes = 0
        
        # 加载配置
        self.config = self.load_config()
        self.progress = self.load_progress()
        
        # 设置日志（必须在check_and_cleanup_logs之前）
        self.setup_logging()
        
        # 运行次数计数器（每20次清理一次日志）
        self.check_and_cleanup_logs()
        
        # 初始化浏览器
        self.setup_driver(headless)
        
        self.logger.info(f"配置文件: {config_file}")
        self.logger.info(f"账号配置: {account_file}")
        self.logger.info(f"进度文件: {self.progress_file}")
        self.logger.info(f"日志文件: {self.log_file}")

    def load_config(self):
        """加载配置文件（从 account.json 和 config.json 两个文件读取）"""
        # 默认配置（只包含通用配置，不包含账号、密码、课程名称）
        default_config = {
            "min_watch_percentage": 0.95,
            "max_videos_per_run": 999,
            "captcha_timeout": 300,
            "enable_notifications": True
        }
        
        # 1. 加载通用配置 config.json
        config_path = os.path.join(self.project_root, '启动', 'config.json')
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 只更新通用配置
                    for key in ['min_watch_percentage', 'max_videos_per_run', 'captcha_timeout', 'enable_notifications']:
                        if key in config:
                            default_config[key] = config[key]
            except Exception as e:
                print(f"加载配置文件失败，使用默认配置: {e}")
        
        # 2. 加载账号配置 account.json（包含账号、密码、课程名称等）
        account_path = os.path.join(self.project_root, '启动', self.account_file)
        
        if os.path.exists(account_path):
            try:
                with open(account_path, 'r', encoding='utf-8') as f:
                    account_config = json.load(f)
                    # 合并账号配置（会覆盖通用配置中的同名项）
                    default_config.update(account_config)
            except Exception as e:
                print(f"加载账号配置文件失败: {e}")
        
        return default_config
    
    def load_progress(self):
        """加载进度记录"""
        default_progress = {
            "completed_videos": [],
            "total_watched": 0,
            "last_update": None,
            "run_count": 0
        }

        if os.path.exists(self.progress_file):
            try:
                # 使用utf-8-sig编码自动处理BOM（字节顺序标记）
                with open(self.progress_file, 'r', encoding='utf-8-sig') as f:
                    loaded_progress = json.load(f)

                if not isinstance(loaded_progress, dict):
                    return default_progress

                merged_progress = default_progress.copy()
                merged_progress.update(loaded_progress)

                if not isinstance(merged_progress.get('completed_videos'), list):
                    merged_progress['completed_videos'] = []
                if not isinstance(merged_progress.get('total_watched'), int):
                    merged_progress['total_watched'] = 0
                if not isinstance(merged_progress.get('run_count'), int):
                    merged_progress['run_count'] = 0

                return merged_progress
            except json.JSONDecodeError as e:
                print(f"⚠️  进度文件解析失败: {e}")
                print(f"⚠️  将使用默认进度，原文件将被覆盖")
                # 删除损坏的文件
                try:
                    os.remove(self.progress_file)
                    print("✅ 已删除损坏的进度文件")
                except:
                    pass
            except Exception as e:
                print(f"加载进度文件失败: {e}")

        return default_progress
    
    def save_progress(self):
        """保存进度记录"""
        try:
            self.progress['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(self.progress, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存进度失败: {e}")
    
    def check_and_cleanup_logs(self):
        """检查运行次数并清理日志文件"""
        # 增加运行次数
        self.progress['run_count'] = self.progress.get('run_count', 0) + 1
        current_run_count = self.progress['run_count']
        
        # 每20次清理一次日志
        if current_run_count % 20 == 0:
            self.cleanup_old_logs()
            self.logger.info(f"📊 当前运行次数: {current_run_count}，已触发日志清理")
        else:
            # 如果还未初始化logger，先打印信息
            if hasattr(self, 'logger'):
                self.logger.info(f"📊 当前运行次数: {current_run_count}/20，距离下次日志清理还剩 {20 - (current_run_count % 20)} 次")
            else:
                print(f"📊 当前运行次数: {current_run_count}/20")
        
        # 保存更新后的运行次数
        self.save_progress()
    
    def cleanup_old_logs(self):
        """清理旧的日志文件内容，保留最近的部分"""
        try:
            if not os.path.exists(self.log_file):
                return
            
            # 读取当前日志文件
            with open(self.log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 备份文件信息
            file_size = os.path.getsize(self.log_file)
            file_size_mb = file_size / (1024 * 1024)
            
            print(f"\n{'='*60}")
            print(f"🧹 开始清理日志文件: {self.log_file}")
            print(f"📊 清理前大小: {file_size_mb:.2f} MB ({len(lines)} 行)")
            
            # 如果日志行数超过10000行，只保留最后5000行
            if len(lines) > 10000:
                # 保留最后5000行
                keep_lines = lines[-5000:]
                
                # 添加清理标记
                cleanup_header = [
                    f"{'='*60}\n",
                    f"日志清理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
                    f"清理说明: 运行20次后自动清理，保留最近5000行\n",
                    f"删除行数: {len(lines) - 5000} 行\n",
                    f"保留行数: 5000 行\n",
                    f"{'='*60}\n\n"
                ]
                
                # 写入清理后的内容
                with open(self.log_file, 'w', encoding='utf-8') as f:
                    f.writelines(cleanup_header)
                    f.writelines(keep_lines)
                
                # 计算清理后的大小
                new_size = os.path.getsize(self.log_file)
                new_size_mb = new_size / (1024 * 1024)
                saved_mb = file_size_mb - new_size_mb
                
                print(f"✅ 清理后大小: {new_size_mb:.2f} MB (5000 行)")
                print(f"💾 节省空间: {saved_mb:.2f} MB")
                print(f"🗑️  删除行数: {len(lines) - 5000} 行")
                print(f"{'='*60}\n")
            else:
                print(f"ℹ️  日志文件不大({len(lines)} 行)，跳过清理")
                print(f"{'='*60}\n")
                
        except Exception as e:
            print(f"❌ 清理日志文件失败: {e}")
            if hasattr(self, 'logger'):
                self.logger.error(f"清理日志文件失败: {e}")
    
    def cleanup_logs_if_needed(self):
        """根据日志大小判断是否需要清理（任务开始/结束时调用）"""
        try:
            if not os.path.exists(self.log_file):
                return
            
            # 检查文件大小
            file_size = os.path.getsize(self.log_file)
            file_size_mb = file_size / (1024 * 1024)
            
            # 如果文件大于20MB，触发清理
            if file_size_mb > 20:
                self.logger.info(f"🚨 日志文件过大({file_size_mb:.2f} MB)，触发清理...")
                self.cleanup_old_logs()
            else:
                self.logger.info(f"📊 日志文件大小: {file_size_mb:.2f} MB，无需清理")
        except Exception as e:
            self.logger.error(f"检查日志文件失败: {e}")

    def setup_logging(self):
        """设置日志记录"""
        # 使用实例变量中的日志文件名
        log_file = self.log_file
        
        # 【修复】确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        # 配置日志格式【修复】Windows下强制UTF-8编码
        handlers = [logging.FileHandler(log_file, encoding='utf-8')]
        
        if sys.platform == 'win32':
            import io
            # 创建UTF-8编码的stream
            utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
            handlers.append(logging.StreamHandler(utf8_stdout))
        else:
            handlers.append(logging.StreamHandler())
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=handlers
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"日志系统初始化完成，日志文件: {log_file}")

    def _resolve_local_driver_paths(self):
        return resolve_local_driver_paths(self.project_root)

    def setup_driver(self, headless=False):
        """设置Chrome浏览器驱动"""
        self.logger.info("🚀 开始初始化ChromeDriver")
        self.logger.info("=" * 60)
        session = create_browser_session(
            self.project_root,
            headless=headless,
            logger=self.logger,
            window_size="1920,1080",
            retry_clean_manager=True,
            check_path_driver=True,
        )
        self.driver = session.driver
        self.wait = session.wait
        self.logger.info("=" * 60)
        self.logger.info("✅ 浏览器驱动初始化完成")
        self.logger.info("=" * 60)

    def smart_wait(self, seconds=None):
        """智能等待，随机延迟避免被检测"""
        if seconds is None:
            seconds = random.uniform(2, 5)
        time.sleep(seconds)
    
    def check_and_close_question_popup(self):
        """检测并关闭题目弹窗（仅用于类型2课程）"""
        try:
            return detect_close_question_popup(self.driver, logger=self.logger, wait_func=self.smart_wait)
        except Exception as e:
            self.logger.error(f"检测题目弹窗时出错: {e}")
            return False
    
    def detect_course_layout(self):
        """检测课程布局类型"""
        try:
            return detect_course_layout_type(self.driver, logger=self.logger)
        except Exception as e:
            self.logger.error(f"检测课程布局时出错: {e}")
            return 'main'  # 默认使用旧版布局
    
    
    def load_account(self):
        """从配置文件加载账号密码、课程名称、课程类型和最大观看时长"""
        try:
            if not os.path.exists(self.account_file):
                print(f"\n❌ 账号配置文件 {self.account_file} 不存在！")
                print(f"请创建 {self.account_file} 文件并填写账号密码")
                print("文件格式：")
                print('{"username": "你的账号", "password": "你的密码", "course_name": "课程名称", "course_type": 1, "max_watch_minutes": 0}')
                raise FileNotFoundError(f"{self.account_file} 不存在")
            
            with open(self.account_file, 'r', encoding='utf-8') as f:
                account = json.load(f)
                username = account.get('username', '').strip()
                password = account.get('password', '').strip()
                course_name = account.get('course_name', '').strip()
                course_url = account.get('course_url', '').strip()  # 【新增】课程URL
                course_type = account.get('course_type', 1)  # 默认为类型1（无题目）
                max_watch_minutes = account.get('max_watch_minutes', 0)  # 默认0（播放完所有）
                
                if not username or not password:
                    print(f"\n❌ 账号或密码为空！")
                    print(f"请在 {self.account_file} 中填写正确的账号和密码")
                    raise ValueError("账号或密码为空")
                
                # 【修改】如果有course_url，course_name可以为空
                if not course_url:
                    # 没有URL，必须提供course_name
                    if not course_name:
                        course_name = self.config.get('course_name', '中国近现代史纲要')
                        self.logger.warning(f"⚠️ account.json中未配置course_name，使用默认值: {course_name}")
                
                # 课程类型说明
                course_type_desc = "无题目课程" if course_type == 1 else "有题目课程（会自动关闭弹题）"
                
                # 观看时长说明
                if max_watch_minutes > 0:
                    watch_time_desc = f"{max_watch_minutes}分钟后停止"
                else:
                    watch_time_desc = "播放完所有视频"
                
                print(f"\n✅ 已加载账号: {username[:3]}****{username[-2:] if len(username) > 5 else '**'}")
                
                # 【新增】显示URL或课程名
                if course_url:
                    print(f"🌐 课程URL: {course_url}")
                    print("✅ 将直接跳转到课程URL，跳过课程查找")
                else:
                    print(f"✅ 目标课程: {course_name}")
                
                print(f"✅ 课程类型: {course_type} - {course_type_desc}")
                print(f"✅ 观看时长: {watch_time_desc}")
                
                # 【修改】返回6个值（新增 course_url）
                return username, password, course_name, course_type, max_watch_minutes, course_url
                
        except FileNotFoundError:
            raise
        except json.JSONDecodeError as e:
            print(f"\n❌ {self.account_file} 文件格式错误: {e}")
            print("请确保JSON格式正确")
            raise
        except Exception as e:
            print(f"\n❌ 读取账号配置失败: {e}")
            raise

    def check_captcha(self):
        """检查是否有人机验证"""
        try:
            return is_captcha_present(self.driver)
        except Exception as e:
            self.logger.error(f"检查验证码时出错: {e}")
            return False

    def wait_for_captcha_completion(self, timeout=None):
        """等待用户完成人机验证"""
        if timeout is None:
            timeout = self.config.get('captcha_timeout', 60)  # 默认60秒，不再是300秒
        
        self.logger.info("检测到人机验证，请手动完成验证...")
        
        # 播放提示音（如果支持）
        if self.config.get('enable_notifications', True):
            try:
                import winsound
                winsound.Beep(1000, 500)  # 1000Hz，持续500ms
            except Exception:
                pass
        return detect_wait_for_captcha_completion(
            self.check_captcha,
            self.check_login_success,
            logger=self.logger,
            timeout=timeout,
        )

    def check_login_success(self):
        """检查是否登录成功"""
        try:
            return is_login_success(self.driver)
        except Exception as e:
            self.logger.error(f"检查登录状态时出错: {e}")
            return False

    def login(self, username=None, password=None):
        """登录知到网站"""
        # 如果没有传入账号密码，从配置文件读取
        if username is None or password is None:
            try:
                username, password, course_name, course_type, max_watch_minutes, course_url = self.load_account()
                # 保存课程名称、类型、最大观看时长和course_url到实例变量
                self.course_name = course_name
                self.course_type = course_type
                self.max_watch_minutes = max_watch_minutes
                self.course_url = course_url  # 【新增】
            except Exception as e:
                self.logger.error(f"加载账号失败: {e}")
                return False
        
        self.logger.info(f"正在登录，账号: {mask_username(username)}")

        try:
            # 打开登录页面
            self.driver.get("https://onlineweb.zhihuishu.com/onlinestuh5")
            self.smart_wait(5)

            # 判断是否需要登录
            need_login = is_login_required(self.driver)

            if need_login:
                self.logger.info("检测到需要登录")
                
                # 尝试多种登录方式
                login_success = self.try_login_methods(username, password)

                if login_success:
                    self.logger.info("登录表单提交成功，等待页面响应...")
                    
                    # 等待并持续检测登录状态（最多30秒）
                    max_wait = 30
                    check_interval = 2
                    elapsed = 0
                    
                    while elapsed < max_wait:
                        self.smart_wait(check_interval)
                        elapsed += check_interval
                        
                        self.logger.info(f"检查登录状态... ({elapsed}/{max_wait}秒)")
                        
                        # 检查是否有人机验证
                        if self.check_captcha():
                            self.logger.info("检测到人机验证，等待用户手动完成")
                            if not self.wait_for_captcha_completion():
                                self.logger.warning("人机验证等待超时或失败")
                                return False
                            # 验证完成后直接跳出循环，不再重复检查
                            self.logger.info("✅ 人机验证已完成，跳过剩余检查")
                            break
                        
                        # 检查登录是否成功
                        if self.check_login_success():
                            self.logger.info("登录成功！")
                            self.logger.info("⏳ 等待5秒，确保页面完全加载...")
                            time.sleep(5)  # 硬等待5秒
                            self.logger.info("✅ 页面加载完成，继续执行")
                            return True
                        
                        # 检查是否还在登录页面
                        current_url = self.driver.current_url
                        if "login" not in current_url.lower():
                            self.logger.info("已离开登录页面，检查最终状态...")
                            self.smart_wait(2)
                            if self.check_login_success():
                                self.logger.info("登录成功！")
                                self.logger.info("⏳ 等待5秒，确保页面完全加载...")
                                time.sleep(5)  # 硬等待5秒
                                self.logger.info("✅ 页面加载完成，继续执行")
                                return True
                    
                    self.logger.warning(f"等待{max_wait}秒后登录状态仍未确认")
                    # 最后再检查一次
                    if self.check_login_success():
                        self.logger.info("最终检查：登录成功！")
                        self.logger.info("⏳ 等待5秒，确保页面完全加载...")
                        time.sleep(5)  # 硬等待5秒
                        self.logger.info("✅ 页面加载完成，继续执行")
                        return True
                    else:
                        self.logger.warning("最终检查：登录状态不确定")
                        return False
                else:
                    self.logger.warning("登录失败，尝试继续操作")
                    return False
            else:
                self.logger.info("当前已登录或无需登录")
                self.logger.info("⏳ 等待5秒，确保页面完全加载...")
                time.sleep(5)  # 硬等待5秒
                self.logger.info("✅ 页面加载完成，继续执行")
                return True

        except Exception as e:
            self.logger.error(f"登录过程中出现错误: {e}")
            return False

    def try_login_methods(self, username, password):
        """尝试多种登录方式"""
        return auth_try_login_methods(
            self.driver,
            self.wait,
            username,
            password,
            logger=self.logger,
            wait_func=self.smart_wait,
        )

    def login_method1(self, username, password):
        """标准登录方式"""
        return auth_login_method_standard(
            self.driver,
            self.wait,
            username,
            password,
            logger=self.logger,
            wait_func=self.smart_wait,
        )

    def login_method2(self, username, password):
        """备用登录方式"""
        return auth_login_method_script(self.driver, username, password, logger=self.logger)

    def find_chinese_history_course(self, course_name=None):
        """查找并点击课程"""
        # 如果没有传入课程名称，尝试从实例变量或config中获取
        if course_name is None:
            course_name = getattr(self, 'course_name', None) or self.config.get('course_name', '中国近现代史纲要')
        return find_and_click_course_by_name(
            self.driver,
            course_name,
            logger=self.logger,
            wait_func=self.smart_wait,
            include_history_fallback=True,
        )

    def find_unwatched_videos(self):
        """查找未观看的视频（不包括PPT）"""
        self.logger.info("正在查找未观看的视频...")

        # 检查是否启用侧边栏布局功能
        use_sidebar = self.config.get('use_sidebar_layout', False)
        
        if use_sidebar:
            # 启用侧边栏布局检测
            self.logger.info("已启用侧边栏布局功能，正在检测布局类型...")
            layout_type = self.detect_course_layout()
            
            if layout_type == 'sidebar':
                # 新版布局：从右侧目录查找
                return self.find_videos_from_sidebar()
            else:
                # 旧版布局：从主区域查找
                return self.find_videos_from_main_area()
        else:
            # 默认使用主区域查找（v3.3.2稳定逻辑）
            self.logger.info("使用默认主区域查找方式（侧边栏功能未启用）")
            return self.find_videos_from_main_area()
    
    def find_videos_from_sidebar(self):
        """从右侧目录侧边栏查找视频"""
        self.logger.info("从右侧目录侧边栏查找视频...")
        try:
            scan_result = discover_sidebar_videos(
                self.driver,
                completed_texts=self.progress.get('completed_videos', []),
                logger=self.logger,
                wait_func=self.smart_wait,
                sidebar_selectors=DEFAULT_SIDEBAR_SELECTORS,
                video_selectors=DEFAULT_SIDEBAR_VIDEO_SELECTORS,
            )
            if scan_result is None:
                self.logger.warning("未找到侧边栏，切换到主区域查找")
                return self.find_videos_from_main_area()

            unwatched_videos = scan_result.unwatched
            self.logger.info(f"\n共找到 {len(unwatched_videos)} 个未观看视频")
            return unwatched_videos
            
        except Exception as e:
            self.logger.error(f"从侧边栏查找视频时出错: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []
    
    def find_videos_from_main_area(self):
        """查找未观看的视频（不包括PPT）"""
        self.logger.info("正在查找未观看的视频...")

        try:
            scan_result = discover_main_area_videos(
                self.driver,
                completed_texts=self.progress.get('completed_videos', []),
                logger=self.logger,
                wait_func=self.smart_wait,
            )
            unwatched_videos = scan_result.unwatched

            self.logger.info(f"\n共找到 {len(unwatched_videos)} 个未观看视频")
            
            # 如果没找到，提供调试信息
            if len(unwatched_videos) == 0:
                self.logger.warning("\n⚠️  未找到视频，请检查：")
                self.logger.warning("1. 是否需要点击某个章节或标签页")
                self.logger.warning("2. 视频是否已全部观看完毕")
            
            return unwatched_videos

        except Exception as e:
            self.logger.error(f"查找视频时出错: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []

    def is_video_completed(self, element):
        """判断视频是否已完成观看（检查特定的class名称）"""
        try:
            return is_catalog_video_completed(element, logger=self.logger)

        except Exception as e:
            # 如果无法判断，默认为未完成
            self.logger.debug(f"  → 判断完成状态失败: {e}")
            return False

    def find_unwatched_ppts(self):
        """查找未观看的PPT/PDF文件"""
        self.logger.info("正在查找PPT/PDF文件...")
        
        unwatched_ppts = []
        
        try:
            # 等待页面加载
            self.smart_wait(5)
            
            # 滚动页面，确保所有元素都加载出来
            self.logger.info("滚动页面加载所有PPT/PDF...")
            for i in range(5):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                self.smart_wait(2)
            
            # 回到顶部
            self.driver.execute_script("window.scrollTo(0, 0);")
            self.smart_wait(2)
            
            # 查找所有元素（支持PPT和PDF）
            all_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), '.ppt')]") + \
                          self.driver.find_elements(By.XPATH, "//*[contains(text(), '.pptx')]") + \
                          self.driver.find_elements(By.XPATH, "//*[contains(text(), '.pdf')]") + \
                          self.driver.find_elements(By.XPATH, "//*[contains(text(), '.PDF')]")
            
            # 去重
            unique_elements = []
            seen_texts = set()
            for element in all_elements:
                try:
                    text = element.text.strip()
                    if text and text not in seen_texts and ('.ppt' in text or '.pptx' in text or '.pdf' in text.lower()):
                        seen_texts.add(text)
                        unique_elements.append(element)
                except:
                    continue
            
            self.logger.info(f"找到 {len(unique_elements)} 个PPT/PDF元素")
            
            # 筛选未观看PPT/PDF
            for idx, element in enumerate(unique_elements):
                try:
                    text = element.text
                    
                    # 跳过包含"作业"的文件
                    if '作业' in text:
                        self.logger.info(f"  → 跳过：作业文件 ({text[:30]}...)")
                        continue
                    
                    # 跳过已完成的文档
                    if self.is_video_completed(element):
                        self.logger.info(f"  → 跳过：已完成文档 ({text[:30]}...)")
                        continue
                    
                    # 跳过已记录的文档
                    if text in self.progress.get('completed_ppts', []):
                        self.logger.info(f"  → 跳过：已记录文档 ({text[:30]}...)")
                        continue
                    
                    # 加入未观看文档列表
                    if element.is_displayed() and element.is_enabled():
                        # 判断文件类型
                        file_type = 'PDF' if '.pdf' in text.lower() else 'PPT'
                        unwatched_ppts.append({
                            'element': element,
                            'text': text[:100],
                            'type': file_type
                        })
                        self.logger.info(f"  → ✅ 找到未观看{file_type}: {text[:50]}...")
                        
                except Exception as e:
                    self.logger.warning(f"处理文档元素 {idx+1} 时出错: {e}")
                    continue
            
            self.logger.info(f"\n共找到 {len(unwatched_ppts)} 个未观看PPT/PDF")
            return unwatched_ppts
            
        except Exception as e:
            self.logger.error(f"查找PPT/PDF时出错: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []
    
    def play_ppt(self, ppt_info):
        """处理单个PPT/PDF文件：点击进入 → 等待1秒 → 退出"""
        element = ppt_info['element']  # 现在可以安全使用element（已在查找前刷新）
        text = ppt_info['text']
        file_type = ppt_info.get('type', 'PPT')  # 获取文件类型，默认PPT
        
        self.logger.info(f"开始处理{file_type}: {text}")
        
        try:
            # 记录当前窗口
            original_windows = self.driver.window_handles
            original_window = self.driver.current_window_handle
            
            # 滚动到元素
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            self.smart_wait(2)
            
            # 点击文档
            element.click()
            self.logger.info(f"已点击{file_type}，等待页面加载...")
            self.smart_wait(3)
            
            # 检查是否打开了新窗口
            current_windows = self.driver.window_handles
            
            if len(current_windows) > len(original_windows):
                # 有新窗口打开，切换到新窗口
                new_window = [w for w in current_windows if w not in original_windows][0]
                self.logger.info("✅ 检测到新窗口，正在切换...")
                self.driver.switch_to.window(new_window)
                self.logger.info(f"已切换到新窗口，URL: {self.driver.current_url}")
            
            # 等待1秒（确保页面加载）
            self.logger.info("等待1秒...")
            self.smart_wait(1)
            
            # 关闭当前窗口并返回原窗口
            if len(current_windows) > len(original_windows):
                self.logger.info(f"关闭{file_type}窗口，返回课程列表...")
                self.driver.close()
                self.driver.switch_to.window(original_window)
            else:
                # 如果没有新窗口，则后退
                self.logger.info("后退返回课程列表...")
                self.driver.back()
            
            self.smart_wait(2)  # 等待2秒
            self.logger.info(f"✅ {file_type}处理完成: {text[:50]}")
            
            # 记录已完成的文档
            if 'completed_ppts' not in self.progress:
                self.progress['completed_ppts'] = []
            self.progress['completed_ppts'].append(text)
            self.save_progress()
            
            return True
            
        except Exception as e:
            self.logger.error(f"处理{file_type}时出错: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            
            # 尝试恢复到原窗口
            try:
                if self.driver.current_window_handle != original_window:
                    self.driver.switch_to.window(original_window)
            except:
                pass
            
            return False

    def is_clickable_video(self, element):
        """判断元素是否是可点击的视频"""
        try:
            text = element.text.lower()

            # 检查是否包含视频相关关键词
            video_keywords = ['视频', '播放', '观看', 'video', 'play', 'watch', 'lecture']
            if any(keyword in text for keyword in video_keywords):
                return True

            # 检查是否有播放按钮
            play_selectors = [
                ".//*[contains(@class, 'play')]",
                ".//*[contains(text(), '播放')]",
                ".//button[contains(@class, 'play')]",
            ]

            for selector in play_selectors:
                try:
                    if element.find_elements(By.XPATH, selector):
                        return True
                except Exception:
                    continue

            return False

        except Exception as e:
            self.logger.error(f"判断可点击视频时出错: {e}")
            return False

    def get_video_duration(self):
        """获取视频实际时长（秒）"""
        duration = playback_get_video_duration(self.driver, logger=self.logger)
        if duration:
            self.logger.info(f"✅ 成功获取视频时长: {duration:.0f}秒 ({duration/60:.1f}分钟)")
        else:
            self.logger.warning("⚠️ 视频时长获取失败，返回None")
        return duration
    
    def is_video_playing(self):
        """检测视频是否正在播放"""
        return playback_is_video_playing(self.driver, logger=self.logger)
    
    def get_video_progress(self):
        """获取视频当前播放进度（秒）"""
        return playback_get_video_progress(self.driver, logger=self.logger)

    def click_video_center_with_offset(self, offset_min=-30, offset_max=30, success_prefix="✅ 已点击视频中央"):
        return playback_click_video_center(
            self.driver,
            logger=self.logger,
            offset_min=offset_min,
            offset_max=offset_max,
            success_message=success_prefix,
        )
    
    def ensure_video_playing(self):
        """确保视频正在播放（使用ActionChains点击视频）"""
        try:
            if not self.is_video_playing():
                self.logger.info("视频未播放，尝试点击视频启动")
                self.click_video_center_with_offset(
                    offset_min=-20,
                    offset_max=20,
                    success_prefix="✅ 已点击视频启动播放"
                )
                
                self.smart_wait(2)
                return self.is_video_playing()
            return True
        except Exception as e:
            self.logger.error(f"确保视频播放时出错: {e}")
            return False

    def play_video(self, video_info):
        """播放单个视频（使用多策略点击机制）"""
        element = video_info['element']
        text = video_info['text']

        self.logger.info(f"开始播放视频: {text}")

        try:
            # 记录当前窗口数量
            original_windows = self.driver.window_handles
            original_window = self.driver.current_window_handle
            
            # 滚动到元素
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            self.smart_wait(1)

            # 多策略点击机制：依次尝试三种点击方式
            click_success = False
            
            # 策略1：常规click()
            try:
                self.logger.info("策略1: 尝试常规点击")
                element.click()
                self.logger.info("✅ 常规点击成功")
                click_success = True
            except Exception as e:
                self.logger.warning(f"常规点击失败: {e}")
            
            # 策略2：ActionChains执行click
            if not click_success:
                try:
                    self.logger.info("策略2: 尝试ActionChains点击")
                    from selenium.webdriver.common.action_chains import ActionChains
                    actions = ActionChains(self.driver)
                    actions.move_to_element(element)
                    actions.click()
                    actions.perform()
                    self.logger.info("✅ ActionChains点击成功")
                    click_success = True
                except Exception as e:
                    self.logger.warning(f"ActionChains点击失败: {e}")
            
            # 策略3：删除（不再使用JavaScript点击坐标）
            # 如果前两个策略都失败，直接返回失败
            # JavaScript点击会触发防脚本检测
            
            if not click_success:
                self.logger.error("❌ 所有点击策略均失败")
                return False
            
            # 等待并检测窗口变化（循环检测，最多10秒）
            new_window = None
            max_wait = 10
            
            for i in range(max_wait):
                self.smart_wait(1)
                current_windows = self.driver.window_handles
                
                # 检测是否有新窗口
                if len(current_windows) > len(original_windows):
                    new_window = [w for w in current_windows if w not in original_windows][0]
                    self.logger.info(f"✅ 检测到新窗口（等待{i+1}秒）")
                    break
                
                # 检测是否是当前URL变化
                try:
                    current_url = self.driver.current_url
                    if 'video' in current_url.lower() or 'play' in current_url.lower():
                        self.logger.info(f"✅ 检测到URL跳转（等待{i+1}秒）: {current_url}")
                        break
                except:
                    pass
                
                if i < max_wait - 1:
                    self.logger.info(f"等待窗口跳转... {i+1}/{max_wait}")
            
            # 切换到新窗口（如果有）
            current_windows = self.driver.window_handles
            if len(current_windows) > len(original_windows):
                new_window = [w for w in current_windows if w not in original_windows][0]
                self.driver.switch_to.window(new_window)
                self.logger.info("已切换到新窗口")
                self.smart_wait(5)
            else:
                self.logger.info("当前窗口跳转")
                self.smart_wait(5)

            # 等待视频播放器加载
            if not self.wait_for_video_player():
                self.logger.warning("视频播放器加载失败")
                if len(current_windows) > len(original_windows):
                    self.driver.close()
                    self.driver.switch_to.window(original_window)
                return False
            
            # 获取视频时长
            video_duration = self.get_video_duration()
            
            # 确保视频开始播放
            self.ensure_video_playing()

            # 模拟观看行为
            self.simulate_watching(video_duration)

            # 记录已完成的视频
            if text not in self.progress['completed_videos']:
                self.progress['completed_videos'].append(text)
                self.progress['total_watched'] += 1
                self.save_progress()
            
            # 【新增】检查是否达到预设观看时间
            if self.max_watch_minutes > 0:
                total_minutes = self.total_watch_time_seconds / 60
                if total_minutes >= self.max_watch_minutes:
                    self.logger.info("\n" + "="*60)
                    self.logger.info(f"✅ 已达到预设观看时间 {self.max_watch_minutes} 分钟")
                    self.logger.info(f"✅ 已播放时间: {total_minutes:.1f} 分钟 ({self.total_watch_time_seconds:.0f} 秒)")
                    self.logger.info("="*60)
                    self.logger.info("🚫 结束播放，跳出循环")
                    # 关闭视频窗口并返回原窗口
                    if len(current_windows) > len(original_windows):
                        self.driver.close()
                        self.driver.switch_to.window(original_window)
                    else:
                        self.go_back_to_course()
                    # 设置标志，在外层循环检查
                    self.reach_time_limit = True
                    return True

            # 关闭视频窗口并返回原窗口
            if len(current_windows) > len(original_windows):
                self.driver.close()
                self.driver.switch_to.window(original_window)
            else:
                self.go_back_to_course()
            
            self.smart_wait(2)
            self.logger.info(f"视频播放完成: {text}")
            return True

        except Exception as e:
            self.logger.error(f"播放视频时出错: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            try:
                if len(self.driver.window_handles) > 1:
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
            except:
                pass
            return False

    def wait_for_video_player(self):
        """等待视频播放器加载"""
        try:
            self.logger.info("等待视频播放器加载...")
            
            # 检查当前页面URL
            current_url = self.driver.current_url
            self.logger.info(f"当前URL: {current_url}")
            
            # 检查是否有iframe
            iframes = self.driver.find_elements(By.XPATH, "//iframe")
            self.logger.info(f"页面中有 {len(iframes)} 个iframe")
            
            # 使用更长的等待时间（30秒）
            long_wait = WebDriverWait(self.driver, 30)
            
            # 尝试在主页面查找video元素
            video_found = False
            try:
                self.logger.info("在主页面查找<video>元素...")
                long_wait.until(EC.presence_of_element_located((By.XPATH, "//video")))
                self.logger.info("✅ 在主页面找到<video>元素")
                video_found = True
            except TimeoutException:
                self.logger.info("主页面未找到<video>元素")
            except Exception as e:
                self.logger.warning(f"查找主页面video元素时出错: {str(e)[:100]}")
            
            # 如果主页面没有video，尝试切换到iframe
            if not video_found and len(iframes) > 0:
                self.logger.info("尝试切换到iframe查找video元素...")
                for i, iframe in enumerate(iframes):
                    try:
                        self.logger.info(f"切换到iframe {i+1}/{len(iframes)}")
                        self.driver.switch_to.frame(iframe)
                        
                        # 在iframe中查找video
                        try:
                            iframe_wait = WebDriverWait(self.driver, 5)
                            iframe_wait.until(EC.presence_of_element_located((By.XPATH, "//video")))
                            self.logger.info(f"✅ 在iframe {i+1}中找到<video>元素")
                            video_found = True
                            break
                        except:
                            self.logger.info(f"iframe {i+1}中没有video元素")
                            # 切回主页面
                            self.driver.switch_to.default_content()
                    except Exception as e:
                        self.logger.warning(f"切换iframe {i+1}失败: {e}")
                        # 确保切回主页面
                        try:
                            self.driver.switch_to.default_content()
                        except:
                            pass
            
            if not video_found:
                self.logger.warning("⚠️ 未找到<video>元素，但尝试继续")
                self.logger.info("请检查保存的调试文件: video_player_page_*.png 和 .html")
            
            # 等待页面稳定
            self.logger.info("等待页面稳定...")
            self.smart_wait(3)
            
            # 点击视频中央区域启动播放
            self.click_video_center()
            
            return True

        except Exception as e:
            self.logger.error(f"等待视频播放器时出错: {e}")
            # 即使出错也尝试继续
            return True
    
    def click_video_center(self):
        """点击视频中央黑色区域启动播放（最可靠的方法）"""
        try:
            video_xpath = selector_value(self.selectors, "video.video_xpath", "//video")
            return start_video_playback(
                self.driver,
                logger=self.logger,
                wait_func=self.smart_wait,
                video_xpath=video_xpath,
            )
        except Exception as e:
            self.logger.warning(f"点击视频中央时出错: {e}")
            return False

    def simulate_watching(self, video_duration=None):
        """模拟观看行为"""
        try:
            # 【修复】如果没有传入视频时长，尝试重新获取
            if video_duration is None:
                self.logger.warning("⚠️ 未传入视频时长，尝试重新获取...")
                self.smart_wait(2)  # 等待视频加载完成
                video_duration = self.get_video_duration()
            
            if video_duration is None or video_duration <= 0:
                # 如果仍然无法获取时长，使用默认值
                self.logger.warning("⚠️ 无法获取视频时长，使用默认观看时间")
                watch_time = random.randint(90, 180)
            else:
                # 根据实际视频时长计算观看时间
                min_percentage = self.config.get('min_watch_percentage', 0.95)
                watch_time = int(video_duration * min_percentage)
                # 添加一些随机性（5-15秒）
                watch_time += random.randint(5, 15)
            
            self.logger.info(f"模拟观看视频，预计时间: {watch_time}秒 ({watch_time/60:.1f}分钟)")
            self.logger.info(f"🎯 目标播放进度: {watch_time}秒，视频总时长: {video_duration if video_duration else '未知'}秒")

            start_time = time.time()
            last_progress_check = 0
            no_progress_count = 0  # 连续无进展次数
            last_check_time = start_time  # 上次检查时间

            while True:
                elapsed = time.time() - start_time
                
                # 获取当前视频实际播放进度
                video_progress = self.get_video_progress()
                
                # 【新增】检查视频是否已经播放完成（达到视频总时长的98%）
                if video_duration and video_progress >= video_duration * 0.98:
                    self.logger.info(f"✅ 视频已播放完成（进度: {video_progress:.0f}秒 >= 总时长98%: {video_duration * 0.98:.0f}秒）")
                    break
                
                # 以实际播放进度为准，达到目标时长就结束
                if video_progress >= watch_time:
                    self.logger.info(f"✅ 视频实际播放进度({video_progress:.0f}秒)已达到目标({watch_time}秒)，播放完成")
                    break
                
                # 也检查等待时间，防止无限等待（最多等待目标时长的2倍）
                if elapsed >= watch_time * 2:
                    self.logger.warning(f"⚠️ 等待时间({int(elapsed)}秒)超过目标时长2倍，强制结束")
                    break
                
                # 每10秒检查一次播放状态和进度
                current_time = time.time()
                if current_time - last_check_time >= 10:
                    last_check_time = current_time
                    
                    # 如果是类型2课程，检测并关闭题目弹窗
                    if hasattr(self, 'course_type') and self.course_type == 2:
                        self.check_and_close_question_popup()
                    
                    # 检查视频是否还在播放
                    if not self.ensure_video_playing():
                        self.logger.warning("视频似乎已停止，尝试恢复播放")
                    
                    # 检查进度是否卡住
                    current_progress = self.get_video_progress()
                    
                    # 如果进度完全没有变化（差距小于1秒）
                    if abs(current_progress - last_progress_check) < 1:
                        no_progress_count += 1
                        self.logger.warning(f"⚠️ 视频进度无变化，连续{no_progress_count}次 ({current_progress:.0f}秒)")
                        
                        # 连续4次无进展就触发恢复（防脚本机制）
                        if no_progress_count >= 4:
                            self.logger.warning(f"⚠️ 连续{no_progress_count}次进度无变化，可能触发防脚本机制，尝试恢复...")
                            self.logger.info("尝试点击视频中央区域恢复播放...")
                            self.click_video_center_with_offset()
                            self.smart_wait(2)
                            no_progress_count = 0  # 重置计数
                    else:
                        # 有进展，重置计数
                        if no_progress_count > 0:
                            self.logger.info(f"✅ 视频恢复正常，进度: {current_progress:.0f}秒")
                        no_progress_count = 0
                    
                    last_progress_check = current_progress
                
                # 每次10秒等待
                time.sleep(10)

                # 随机用户行为（降低频率）
                if random.random() < 0.2:  # 20%概率
                    # 随机滚动
                    scroll_amount = random.randint(-100, 100)
                    self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")

                # 显示进度（以实际播放进度为准）
                display_progress = self.get_video_progress()
                safe_watch_time = max(1, watch_time)
                progress_percentage = min(100, int((display_progress / safe_watch_time) * 100))
                total_minutes = (self.total_watch_time_seconds + display_progress) / 60
                self.logger.info(f"观看进度: {progress_percentage}% ({display_progress:.0f}/{watch_time}秒) | 等待时间: {int(elapsed)}秒 | 视频总长: {video_duration if video_duration else '未知'}秒 | 已播放时间: {total_minutes:.1f}分钟")

            # 累加本次实际播放时间到总观看时间
            actual_watch_time = self.get_video_progress()
            self.total_watch_time_seconds += actual_watch_time
            
            # 显示累计观看时间
            total_minutes = self.total_watch_time_seconds / 60
            self.logger.info(f"视频观看完成，本次播放: {actual_watch_time:.0f}秒 ({actual_watch_time/60:.1f}分钟)")
            self.logger.info(f"📊 已播放时间: {total_minutes:.1f}分钟 ({self.total_watch_time_seconds:.0f}秒)")

        except Exception as e:
            self.logger.error(f"模拟观看时出错: {e}")

    def go_back_to_course(self):
        """返回课程列表"""
        try:
            # 尝试多种返回方式
            back_selectors = [
                "//button[contains(text(), '返回')]",
                "//button[contains(@class, 'back')]",
                "//a[contains(text(), '返回')]",
                "//span[contains(text(), '返回')]",
                "//*[contains(@class, 'back-btn')]",
            ]

            for selector in back_selectors:
                try:
                    back_btn = self.driver.find_element(By.XPATH, selector)
                    back_btn.click()
                    self.logger.info("点击返回按钮成功")
                    self.smart_wait(3)
                    return
                except Exception as e:
                    self.logger.warning(f"尝试返回按钮 {selector} 失败: {e}")
                    continue

            # 如果没找到返回按钮，使用浏览器后退
            self.driver.back()
            self.logger.info("使用浏览器后退")
            self.smart_wait(3)
            
            # 验证是否成功返回课程列表
            if not self.verify_course_list():
                self.logger.warning("可能未成功返回课程列表")

        except Exception as e:
            self.logger.error(f"返回课程列表时出错: {e}")
    
    def verify_course_list(self):
        """验证是否在课程列表页面"""
        try:
            return is_course_list_page(self.driver)
        except Exception as e:
            self.logger.error(f"验证课程列表时出错: {e}")
            return False

    def is_course_page_ready(self):
        """判断是否已进入可继续播放的课程页面"""
        return detect_course_page_ready(self.driver)

    def try_click_enter_study(self):
        """尝试点击进入学习按钮"""
        return detect_try_click_enter_study(
            self.driver,
            logger=self.logger,
            wait_func=self.smart_wait,
        )

    def wait_for_course_page_ready(self, timeout_seconds=600):
        """等待进入课程页面并在需要时尝试自动点击进入学习"""
        return detect_wait_for_course_page_ready(
            self.driver,
            logger=self.logger,
            wait_func=self.smart_wait,
            timeout_seconds=timeout_seconds,
        )

    def run(self, username=None, password=None, max_videos=None):
        """运行自动播放程序"""
        # 任务开始时清理日志
        self.logger.info("\n" + "="*60)
        self.logger.info("📋 任务开始 - 检查日志文件")
        self.logger.info("="*60)
        self.cleanup_logs_if_needed()
        
        # 重要：每次任务开始时清空已完成视频记录
        # 避免播放失败的视频被错误记录后永久跳过
        old_count = len(self.progress.get('completed_videos', []))
        self.progress['completed_videos'] = []  # 清空已完成视频列表
        self.save_progress()  # 立即保存
        self.logger.info("\n" + "="*60)
        self.logger.info("🗑️  已清空本次任务的视频记录")
        if old_count > 0:
            self.logger.info(f"📊 清空了 {old_count} 条旧记录")
        self.logger.info("🎯 本次任务将重新扫描所有视频")
        self.logger.info("✅ 避免之前播放失败的视频被跳过")
        self.logger.info("="*60)
        
        # 如果没有传入账号密码，从 account.json 读取
        if username is None or password is None:
            try:
                username, password, course_name, course_type, max_watch_minutes, course_url = self.load_account()
                # 保存课程名称、类型、最大观看时长和course_url到实例变量
                self.course_name = course_name
                self.course_type = course_type
                self.max_watch_minutes = max_watch_minutes
                self.course_url = course_url  # 【新增】
                # 显示时间限制配置
                if self.max_watch_minutes > 0:
                    self.logger.info(f"⏰ 预设观看时间限制: {self.max_watch_minutes} 分钟")
                else:
                    self.logger.info("⏰ 未设置观看时间限制，将播放所有视频")
            except Exception as e:
                self.logger.error(f"加载账号失败: {e}")
                self.logger.error("请在 account.json 中配置账号密码后重试")
                return
        
        if max_videos is None:
            max_videos = self.config.get('max_videos_per_run', 999)  # 默认999，基本相当于无限
        
        self.logger.info("="*60)
        self.logger.info("开始知到网页版自动播放程序")
        self.logger.info("="*60)
        self.logger.info("⚠️  重要提示：请不要手动关闭浏览器窗口！")
        self.logger.info("⚠️  程序会自动控制浏览器，请等待程序完成")
        self.logger.info("="*60)
        self.logger.info(f"已观看视频数: {self.progress['total_watched']}")
        if max_videos >= 999:
            self.logger.info("播放模式: 持续播放直到所有视频完成")
        else:
            self.logger.info(f"本次最多播放: {max_videos} 个视频")
        self.logger.info("="*60)

        try:
            # 登录
            if not self.login(username, password):
                self.logger.warning("⚠️ 登录失败，等待用户手动登录...")
                waited = 0
                while waited < 600:
                    try:
                        if self.check_login_success():
                            self.logger.info("✅ 已检测到登录成功")
                            break
                    except Exception:
                        pass
                    time.sleep(2)
                    waited += 2

            # 【新增】检查是否有course_url，决定是否跳过课程查找
            if has_course_url(getattr(self, 'course_url', '')):
                if not open_course_url(
                    self.driver,
                    self.course_url,
                    wait_ready_func=self.wait_for_course_page_ready,
                    logger=self.logger,
                    wait_func=self.smart_wait,
                ):
                    return
            else:
                # 没有URL，使用传统的课程查找
                if not self.find_chinese_history_course():
                    self.logger.warning("⚠️ 未找到课程，等待用户手动进入课程页面...")
                    if not self.wait_for_course_page_ready():
                        return

            # 循环处理视频，直到所有视频播放完成或达到时间限制
            videos_played = 0
            attempt = 0
            
            # 【新增】初始化时间限制标志
            self.reach_time_limit = False
            
            # 第一次查找未观看视频（入口处查找）
            self.logger.info("🔍 查找未观看的视频...")
            unwatched_videos = self.find_unwatched_videos()
            
            if not unwatched_videos:
                self.logger.info("✅ 没有找到更多未观看视频，所有视频已播放完成！")
            else:
                self.logger.info(f"✅ 找到 {len(unwatched_videos)} 个未观看视频，将逐个播放")
            
            while attempt < max_videos and unwatched_videos:
                # 检查是否达到最大观看时长
                if hasattr(self, 'max_watch_minutes') and self.max_watch_minutes > 0:
                    total_minutes = self.total_watch_time_seconds / 60
                    if total_minutes >= self.max_watch_minutes:
                        self.logger.info("\n" + "="*60)
                        self.logger.info(f"✅ 已达到最大观看时长 {self.max_watch_minutes} 分钟")
                        self.logger.info(f"✅ 累计观看时间: {total_minutes:.1f} 分钟 ({self.total_watch_time_seconds:.0f} 秒)")
                        self.logger.info("="*60)
                        break
                attempt += 1
                self.logger.info(f"\n=== 第 {attempt} 轮播放 ====")
                
                # 智能刷新：每10次查找前刷新一次页面
                if self.items_processed_since_refresh >= self.refresh_interval:
                    self.logger.info(f"已处理{self.items_processed_since_refresh}个项目，刷新页面以更新状态...")
                    self.driver.refresh()
                    self.smart_wait(3)
                    self.items_processed_since_refresh = 0  # 重置计数器
                    unwatched_videos = []  # 清空缓存，刷新后重新查找
                elif self.items_processed_since_refresh > 0:
                    self.logger.info(f"已处理{self.items_processed_since_refresh}个项目（每{self.refresh_interval}次刷新一次）")

                # 每10次查找一次（或缓存为空时重新查找）
                # 注意：attempt从1开始，第一轮不需要查找（已经在入口处查找过）
                if not unwatched_videos or (attempt > 1 and (attempt - 1) % 10 == 0):
                    self.logger.info("🔍 查找未观看的视频...")
                    unwatched_videos = self.find_unwatched_videos()
                    
                    if not unwatched_videos:
                        self.logger.info("✅ 没有找到更多未观看视频，所有视频已播放完成！")
                        break
                    
                    self.logger.info(f"✅ 找到 {len(unwatched_videos)} 个未观看视频，将逐个播放")
                else:
                    self.logger.info(f"📦 使用缓存的视频列表（剩余 {len(unwatched_videos)} 个）")
                
                if not unwatched_videos:
                    self.logger.info("✅ 没有更多视频，结束播放")
                    break

                # 播放第一个未观看视频
                video_to_play = unwatched_videos.pop(0)  # 从v3.3.1的简单逻辑
                play_result = self.play_video(video_to_play)
                
                if play_result:
                    videos_played += 1
                    self.items_processed_since_refresh += 1
                    self.logger.info(f"✅ 成功播放第 {videos_played} 个视频")
                    
                    # 【新增】检查是否达到时间限制
                    if self.reach_time_limit:
                        self.logger.info("🚫 已达到预设观看时间，退出播放循环")
                        break
                else:
                    self.logger.warning("⚠️ 播放失败，尝试恢复或等待人工介入")
                    # 尝试恢复播放
                    if self.ensure_video_playing():
                            self.logger.info("✅ 已恢复播放")
                    else:
                            # 尝试关闭可能的弹窗
                            try:
                                dialogs = self.driver.find_elements(By.XPATH, "//*[@role='dialog' or contains(@class,'dialog') or contains(@class,'el-dialog__wrapper')]")
                                if dialogs:
                                    close_btns = self.driver.find_elements(By.XPATH, "//button[contains(.,'同意') or contains(.,'确认') or contains(.,'关闭') or contains(.,'知道了')] | //i[contains(@class,'iconguanbi')]")
                                    if close_btns:
                                        try:
                                            close_btns[0].click()
                                        except Exception:
                                            pass
                            except Exception:
                                pass
                            
                            # 人工介入等待：提示用户手动点击播放或关闭弹窗
                            self.logger.info("🔔 请手动点击播放或关闭弹窗，程序将等待恢复播放...")
                            waited_manual = 0
                            while waited_manual < 600:
                                try:
                                    if self.is_video_playing():
                                        self.logger.info("✅ 检测到视频已开始播放")
                                        break
                                except Exception:
                                    pass
                                time.sleep(2)
                                waited_manual += 2

                # 随机延迟
                self.smart_wait()

            # 显示最终统计
            self.logger.info("\n" + "="*60)
            if videos_played > 0:
                self.logger.info(f"✅ 自动播放程序完成，本次播放 {videos_played} 个视频")
            else:
                self.logger.info("✅ 所有视频已播放完成，无需播放")
            self.logger.info(f"✅ 总计已观看: {self.progress['total_watched']} 个视频")
            # 【新增】显示总播放时间
            total_minutes = self.total_watch_time_seconds / 60
            self.logger.info(f"📊 本次总播放时间: {total_minutes:.1f}分钟 ({self.total_watch_time_seconds:.0f}秒)")
            self.logger.info("="*60)

            # ========== 新增：PPT处理部分 ==========
            self.logger.info("\n" + "="*60)
            self.logger.info("📄 开始处理PPT文件...")
            self.logger.info("="*60)
            
            # 循环处理PPT，每10次查找一次
            ppts_processed = 0
            ppt_attempt = 0
            max_ppt_attempts = 200  # 最多尝试200次
            unwatched_ppts = []  # 缓存查找到的PPT列表
            
            while ppt_attempt < max_ppt_attempts:
                ppt_attempt += 1
                
                # 智能刷新：每10次处理前检查
                if self.items_processed_since_refresh >= self.refresh_interval:
                    self.logger.info(f"已处理{self.items_processed_since_refresh}个项目，刷新页面以更新状态...")
                    self.driver.refresh()
                    self.smart_wait(3)
                    self.items_processed_since_refresh = 0  # 重置计数器
                    unwatched_ppts = []  # 清空缓存，刷新后重新查找
                elif self.items_processed_since_refresh > 0:
                    self.logger.info(f"已处理{self.items_processed_since_refresh}个项目（每{self.refresh_interval}次刷新一次）")
                
                # 每10次查找一次（或缓存为空时重新查找）
                if not unwatched_ppts or (ppt_attempt - 1) % 10 == 0:
                    self.logger.info("🔍 查找未PPT...")
                    unwatched_ppts = self.find_unwatched_ppts()
                    
                    if not unwatched_ppts:
                        self.logger.info("✅ 没有找到更多PPT")
                        break
                    
                    self.logger.info(f"✅ 找到 {len(unwatched_ppts)} 个未PPT，将逐个处理")
                else:
                    self.logger.info(f"📦 使用缓存的PPT列表（剩余 {len(unwatched_ppts)} 个）")
                
                if not unwatched_ppts:
                    self.logger.info("✅ 没有更多PPT，结束处理")
                    break
                
                # 处理第一个PPT
                ppt_to_process = unwatched_ppts.pop(0)  # 从列表中取出第一个
                self.logger.info(f"\n=== 处理PPT {ppts_processed + 1} ===")
                
                if self.play_ppt(ppt_to_process):
                    ppts_processed += 1
                    self.items_processed_since_refresh += 1  # 增加计数器
                    self.logger.info(f"✅ 成功处理第 {ppts_processed} 个PPT")
                else:
                    self.logger.warning(f"⚠️ 处理PPT失败")
                
                # 随机延迟
                self.smart_wait()
            
            self.logger.info("\n" + "="*60)
            if ppts_processed > 0:
                self.logger.info(f"✅ PPT处理完成，共处理 {ppts_processed} 个PPT")
            else:
                self.logger.info("✅ 没有找到未PPT")
            self.logger.info("="*60)

        except KeyboardInterrupt:
            self.logger.info("\n" + "="*60)
            self.logger.info("程序被用户中断 (Ctrl+C)")
            self.logger.info("="*60)
        except Exception as e:
            self.logger.error("\n" + "="*60)
            self.logger.error(f"程序运行出错: {e}")
            self.logger.error("如果是浏览器关闭错误，请下次保持浏览器窗口打开！")
            self.logger.error("="*60)
        finally:
            # 任务结束时清理日志
            self.logger.info("\n" + "="*60)
            self.logger.info("📋 任务结束 - 检查日志文件")
            self.logger.info("="*60)
            self.cleanup_logs_if_needed()
            
            # 关闭浏览器
            if self.driver:
                try:
                    self.driver.quit()
                    self.logger.info("\n" + "="*60)
                    self.logger.info("浏览器已正常关闭")
                    self.logger.info("="*60)
                except Exception:
                    pass


def main():
    """主函数"""
    # 添加命令行参数解析
    parser = argparse.ArgumentParser(
        description='知到网页版自动播放程序',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:
  # 使用默认配置文件
  python zhidao_web_auto_player_final.py
  
  # 指定账号配置文件
  python zhidao_web_auto_player_final.py --account account1.json
  
  # 同时运行多个账号（分别在不同终端执行）
  python zhidao_web_auto_player_final.py --account account1.json
  python zhidao_web_auto_player_final.py --account account2.json
  python zhidao_web_auto_player_final.py --account account3.json
  
  # 使用无头模式
  python zhidao_web_auto_player_final.py --account account1.json --headless
        ''')
    
    parser.add_argument(
        '--account',
        default='account.json',
        help='账号配置文件路径 (默认: account.json)'
    )
    
    parser.add_argument(
        '--config',
        default='config.json',
        help='程序配置文件路径 (默认: config.json)'
    )
    
    parser.add_argument(
        '--headless',
        action='store_true',
        help='是否使用无头模式运行（不显示浏览器窗口）'
    )
    
    args = parser.parse_args()
    
    # 显示启动信息
    print("\n" + "="*60)
    print("知到网页版自动播放程序 - 多实例支持版")
    print("="*60)
    print(f"账号配置: {args.account}")
    print(f"程序配置: {args.config}")
    print(f"运行模式: {'\u65e0\u5934\u6a21\u5f0f' if args.headless else '\u6709\u754c\u9762\u6a21\u5f0f'}")
    print("="*60 + "\n")
    
    # 创建播放器实例，传入配置文件路径
    player = ZhidaoWebAutoPlayerFinal(
        headless=args.headless,
        config_file=args.config,
        account_file=args.account
    )

    try:
        # 运行自动播放（使用配置文件中的账号密码）
        player.run()
    except Exception as e:
        print(f"\n程序异常: {e}")


if __name__ == "__main__":
    main()

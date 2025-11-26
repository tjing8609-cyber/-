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

知到网页版自动播放脚本 - 有题目版本 (v2.0)
支持自动播放、题目弹窗处理、侧边栏导航、新版布局支持
"""

import time
import json
import os
import sys
import random
import logging
import threading
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains


def bezier_curve(start, end, control1=None, control2=None, steps=20):
    """
    生成贝塞尔曲线路径点（带随机偏差）
    
    Args:
        start: 起点 (x, y)
        end: 终点 (x, y)
        control1: 控制点1 (x, y)，如果为None则自动生成
        control2: 控制点2 (x, y)，如果为None则自动生成
        steps: 路径点数量
    
    Returns:
        路径点列表 [(x1, y1), (x2, y2), ...]
    """
    x0, y0 = start
    x3, y3 = end
    
    # 自动生成控制点，创建自然的曲线
    if control1 is None:
        # 控制点1在起点和终点之间偏移
        offset_x = random.uniform(-50, 50)
        offset_y = random.uniform(-30, 30)
        x1 = x0 + (x3 - x0) * 0.25 + offset_x
        y1 = y0 + (y3 - y0) * 0.25 + offset_y
    else:
        x1, y1 = control1
    
    if control2 is None:
        # 控制点2在起点和终点之间偏移
        offset_x = random.uniform(-50, 50)
        offset_y = random.uniform(-30, 30)
        x2 = x0 + (x3 - x0) * 0.75 + offset_x
        y2 = y0 + (y3 - y0) * 0.75 + offset_y
    else:
        x2, y2 = control2
    
    # 生成贝塞尔曲线路径点
    points = []
    for i in range(steps + 1):
        t = i / steps
        # 三次贝塞尔曲线公式
        x = (1-t)**3 * x0 + 3*(1-t)**2*t * x1 + 3*(1-t)*t**2 * x2 + t**3 * x3
        y = (1-t)**3 * y0 + 3*(1-t)**2*t * y1 + 3*(1-t)*t**2 * y2 + t**3 * y3
        
        # 【反检测优化】为每个路径点添加随机像素偏差（5-10像素）
        # 注意：最后一个点（终点）不添加偏差，确保准确到达目标
        if i < steps:  # 不是终点
            deviation_x = random.uniform(-10, 10)  # 上下偏差
            deviation_y = random.uniform(-10, 10)  # 左右偏差
            x += deviation_x
            y += deviation_y
        
        points.append((int(x), int(y)))
    
    return points


class ZhidaoWebAutoPlayerWithQuiz:
    """知到网页版自动播放器 - 有题目版本"""
    
    def __init__(self, account_file='account.json', headless=False):
        """初始化播放器"""
        self.account_file = account_file
        
        # 【新增】线程控制变量
        self.quiz_detected = threading.Event()  # 题目检测事件
        self.quiz_handling = False  # 是否正在处理题目
        self.monitor_running = True  # 监控线程运行标志
        self.quiz_monitor_thread = None  # 题目监控线程
        
        # 加载配置
        self.config = self.load_config()
        self.account_config = self.load_account_config()
        
        # 【重要】先设置日志，因为后续方法会使用logger
        self.setup_logging()
        
        # 加载进度（需要使用logger）
        self.progress = self.load_progress()
        
        # 运行次数计数器（每20次清理一次日志）
        self.check_and_cleanup_logs()
        
        # 初始化刷新计数器（每10次才刷新一次）
        self.items_processed_since_refresh = 0
        self.refresh_interval = 10  # 每10个项目刷新一次
        
        # 初始化累计观看时间（秒）
        self.total_watch_time_seconds = 0
        
        # 【新增】读取预设观看时间限制（分钟）
        self.max_watch_minutes = self.account_config.get('max_watch_minutes', 0)
        if self.max_watch_minutes > 0:
            self.logger.info(f"⏰ 预设观看时间限制: {self.max_watch_minutes} 分钟")
        else:
            self.logger.info("⏰ 未设置观看时间限制，将播放所有视频")
        
        # 初始化浏览器
        self.setup_driver(headless)
        
        # 视频播放统计
        self.videos_watched_this_session = 0
        self.quizzes_answered_this_session = 0
        
        self.logger.info("="*60)
        self.logger.info("知到网页版自动播放器 - 有题目版本 v2.0")
        self.logger.info("="*60)
    
    def setup_logging(self):
        """设置日志系统"""
        # 获取项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # 从account文件名提取账号编号（只取文件名，去除路径）
        account_filename = os.path.basename(self.account_file)
        account_num = account_filename.replace('account', '').replace('.json', '')
        if not account_num:
            account_num = '1'
        
        log_file = os.path.join(project_root, 'log', f'zhidao_account{account_num}_quiz.log')
        
        # 【修复】确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        # 配置日志
        self.logger = logging.getLogger(f'ZhidaoQuiz_{account_num}')
        self.logger.setLevel(logging.INFO)
        
        # 清除已有的处理器
        self.logger.handlers.clear()
        
        # 文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # 控制台处理器【修复】Windows下强制UTF-8编码
        if sys.platform == 'win32':
            import io
            # 创建UTF-8编码的stream
            utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
            console_handler = logging.StreamHandler(utf8_stdout)
        else:
            console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 格式化
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def check_and_cleanup_logs(self):
        """检查并清理日志文件（启动时调用）"""
        # 获取项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        account_filename = os.path.basename(self.account_file)
        account_num = account_filename.replace('account', '').replace('.json', '')
        if not account_num:
            account_num = '1'
        
        log_file = os.path.join(project_root, 'log', f'zhidao_account{account_num}_quiz.log')
        
        # 检查日志文件大小，如果超过20MB则清理
        if os.path.exists(log_file):
            file_size = os.path.getsize(log_file) / (1024 * 1024)  # MB
            if file_size > 20:
                try:
                    # 读取现有日志
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    
                    # 如果超过10000行，保留最后5000行
                    if len(lines) > 10000:
                        # 添加清理标记
                        cleanup_header = [
                            "="*60 + "\n",
                            "🧹 日志文件已清理\n",
                            f"清理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
                            f"清理说明: 日志文件超过{file_size:.1f}MB，已清理并保留最近5000行\n",
                            f"删除行数: {len(lines) - 5000}\n",
                            f"保留行数: 5000\n",
                            "="*60 + "\n\n"
                        ]
                        
                        # 保留最后5000行
                        new_content = cleanup_header + lines[-5000:]
                        
                        # 写回文件
                        with open(log_file, 'w', encoding='utf-8') as f:
                            f.writelines(new_content)
                        
                        new_size = os.path.getsize(log_file) / (1024 * 1024)
                        print(f"✅ 日志文件已清理: {log_file}")
                        print(f"   原大小: {file_size:.2f}MB -> 新大小: {new_size:.2f}MB")
                        print(f"   节省空间: {file_size - new_size:.2f}MB ({(file_size - new_size) / file_size * 100:.1f}%)")
                    else:
                        print(f"ℹ️  日志文件大小: {file_size:.2f}MB，行数: {len(lines)}，无需清理")
                except Exception as e:
                    print(f"清理日志失败: {e}")
            else:
                print(f"✅ 日志文件大小: {file_size:.2f}MB，无需清理")
    
    def load_config(self):
        """加载全局配置"""
        # 获取项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(project_root, '启动', 'config.json')
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                "max_videos_per_run": 999,
                "captcha_timeout": 300,
                "enable_notifications": True
            }
    
    def load_account_config(self):
        """加载账号配置"""
        with open(self.account_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
            # 【新增】提取course_url
            self.course_url = config.get('course_url', '').strip()
            
            return config
    
    def load_progress(self):
        """加载进度记录"""
        # 获取项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        account_filename = os.path.basename(self.account_file)
        account_num = account_filename.replace('account', '').replace('.json', '')
        if not account_num:
            account_num = '1'
        
        progress_file = os.path.join(project_root, 'log', f'progress_account{account_num}.json')
        
        if os.path.exists(progress_file):
            try:
                # 使用utf-8-sig编码自动处理BOM（字节顺序标记）
                with open(progress_file, 'r', encoding='utf-8-sig') as f:
                    progress = json.load(f)
                    
                    # 【向后兼容】确保必要的键存在
                    if 'total_quizzes' not in progress:
                        progress['total_quizzes'] = 0
                    if 'total_watched' not in progress:
                        progress['total_watched'] = 0
                    if 'completed_videos' not in progress:
                        progress['completed_videos'] = []
                    if 'last_run' not in progress:
                        progress['last_run'] = None
                    
                    # 【重要】每次任务开始时，清空本次任务的视频记录列表
                    # 保留累计统计数据，但清空completed_videos作为本次任务的中间变量
                    self.logger.info("")
                    self.logger.info("="*60)
                    self.logger.info("🗑️  已清空本次任务的视频记录")
                    self.logger.info("🎯 本次任务将重新扫描所有视频")
                    self.logger.info("✅ 避免之前播放失败的视频被跳过")
                    self.logger.info("="*60)
                    progress['completed_videos'] = []  # 清空视频记录，作为本次任务的临时变量
                        
                    return progress
            except json.JSONDecodeError as e:
                # JSON解析错误，记录日志并返回默认值
                self.logger.warning(f"⚠️  进度文件解析失败: {e}")
                self.logger.warning(f"⚠️  将使用默认进度，原文件将被覆盖")
                # 删除损坏的文件
                try:
                    os.remove(progress_file)
                    self.logger.info("✅ 已删除损坏的进度文件")
                except:
                    pass
                
        return {
            'total_watched': 0,
            'total_quizzes': 0,
            'completed_videos': [],
            'last_run': None
        }
    
    def save_progress(self):
        """保存进度记录"""
        # 获取项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        account_filename = os.path.basename(self.account_file)
        account_num = account_filename.replace('account', '').replace('.json', '')
        if not account_num:
            account_num = '1'
        
        progress_file = os.path.join(project_root, 'log', f'progress_account{account_num}.json')
        
        self.progress['last_run'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(self.progress, f, indent=2, ensure_ascii=False)
    
    def setup_driver(self, headless=False):
        """设置Chrome浏览器驱动（国内镜像优化）"""
        chrome_options = Options()
        
        if headless:
            chrome_options.add_argument('--headless')
        
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1349,768')  # 设置窗口大小
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        # 禁用自动化提示
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            # 【优化】优先尝试国内镜像下载
            try:
                self.logger.info("🌐 尝试使用国内镜像下载ChromeDriver...")
                os.environ['WDM_SSL_VERIFY'] = '0'
                
                from webdriver_manager.core.download_manager import WDMDownloadManager
                
                class TaobaoMirrorManager(WDMDownloadManager):
                    def download_file(self, url):
                        if 'chromedriver.storage.googleapis.com' in url or 'edgedl.me.gvt1.com' in url:
                            import re
                            version_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', url)
                            if version_match:
                                version = version_match.group(1)
                                url = f'https://registry.npmmirror.com/-/binary/chromedriver/{version}/chromedriver_win32.zip'
                        return super().download_file(url)
                
                try:
                    service = Service(ChromeDriverManager(download_manager=TaobaoMirrorManager()).install())
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    self.logger.info("✅ 使用国内镜像下载成功")
                except:
                    self.logger.info("🔄 镜像下载失败，尝试官方源...")
                    service = Service(ChromeDriverManager().install())
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    self.logger.info("✅ 使用官方源下载成功")
                    
            except Exception as download_error:
                self.logger.warning(f"⚠️  webdriver-manager下载失败: {str(download_error)[:100]}")
                self.logger.info("🔄 尝试使用系统环境中的ChromeDriver...")
                
                try:
                    self.driver = webdriver.Chrome(options=chrome_options)
                    self.logger.info("✅ 使用系统 ChromeDriver 初始化成功")
                except Exception as system_error:
                    self.logger.error(f"❌ 系统ChromeDriver也失败: {system_error}")
                    self.logger.error("\n解决方案：")
                    self.logger.error("1. 手动下载ChromeDriver: https://registry.npmmirror.com/binary.html?path=chromedriver/")
                    self.logger.error("2. 将chromedriver.exe放入系统PATH或当前目录")
                    self.logger.error("3. 或使用VPN后重试自动下载")
                    raise

            # 隐藏自动化特征
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.wait = WebDriverWait(self.driver, 30)
            self.logger.info("浏览器驱动初始化完成")
        except Exception as e:
            self.logger.error(f"浏览器驱动初始化失败: {e}")
            raise
    
    def smart_wait(self, seconds):
        """智能等待（随机波动）"""
        actual_wait = seconds + random.uniform(-0.5, 0.5)
        time.sleep(max(0.5, actual_wait))
    
    def move_to_element_with_curve(self, element):
        """
        使用贝塞尔曲线移动鼠标到元素并点击
        
        Args:
            element: 目标元素
        
        Returns:
            bool: 是否成功
        """
        try:
            # 获取元素位置和尺寸
            element_location = element.location
            element_size = element.size
            
            # 计算目标位置（元素中心点）
            target_x = element_location['x'] + element_size['width'] / 2
            target_y = element_location['y'] + element_size['height'] / 2
            
            # 获取当前鼠标位置（简化处理，使用窗口中心作为起点）
            window_size = self.driver.get_window_size()
            start_x = window_size['width'] / 2
            start_y = window_size['height'] / 2
            
            # 生成贝塞尔曲线路径（15-25个点之间随机）
            steps = random.randint(15, 25)
            curve_points = bezier_curve(
                start=(start_x, start_y),
                end=(target_x, target_y),
                steps=steps
            )
            
            # 使用ActionChains沿曲线移动
            actions = ActionChains(self.driver)
            
            # 移动到起点
            actions.move_by_offset(curve_points[0][0] - start_x, curve_points[0][1] - start_y)
            
            # 沿曲线移动，每次移动添加随机延时
            for i in range(1, len(curve_points)):
                prev_x, prev_y = curve_points[i-1]
                curr_x, curr_y = curve_points[i]
                
                # 计算相对偏移
                offset_x = curr_x - prev_x
                offset_y = curr_y - prev_y
                
                # 移动到下一个点
                actions.move_by_offset(offset_x, offset_y)
                
                # 【反检测】随机暂停时间（0.01-0.05秒）
                if random.random() < 0.3:  # 30%概率暂停
                    actions.pause(random.uniform(0.01, 0.05))
            
            # 移动到目标元素
            actions.move_to_element(element)
            
            # 【反检测】到达目标后短暂停顿（模拟人类瞄准）
            actions.pause(random.uniform(0.1, 0.3))
            
            # 点击
            actions.click()
            
            # 执行动作链
            actions.perform()
            
            self.logger.debug(f"✅ 曲线移动并点击成功（路径点数: {steps}）")
            return True
            
        except Exception as e:
            self.logger.debug(f"曲线移动失败: {e}，使用普通点击")
            try:
                element.click()
                return True
            except:
                return False
    
    def login(self, username=None, password=None):
        """登录知到网站（完全模仿原版本）"""
        # 如果没有传入账号密码，从配置文件读取
        if username is None or password is None:
            username = self.account_config.get('username')
            password = self.account_config.get('password')
        
        self.logger.info(f"正在登录，账号: {username[:3]}****{username[-2:] if len(username) > 5 else '**'}")

        try:
            # 打开登录页面
            self.driver.get("https://onlineweb.zhihuishu.com/onlinestuh5")
            self.smart_wait(5)

            # 检查当前页面状态
            current_url = self.driver.current_url
            page_source = self.driver.page_source

            # 判断是否需要登录
            need_login = any([
                "login" in current_url.lower(),
                "登录" in page_source,
                "手机号" in page_source,
                "password" in page_source.lower()
            ])

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
        login_methods = [
            self.login_method1,  # 标准登录方式
            self.login_method2,  # 备用登录方式
        ]

        for method in login_methods:
            try:
                if method(username, password):
                    return True
            except Exception as e:
                self.logger.warning(f"登录方式 {method.__name__} 失败: {e}")
                continue

        return False

    def login_method1(self, username, password):
        """标准登录方式"""
        self.logger.info("尝试标准登录方式1...")
        
        # 查找用户名输入框
        username_selectors = [
            "//input[@type='text']",
            "//input[@placeholder='手机号']",
            "//input[contains(@placeholder, '账号')]",
            "//input[contains(@placeholder, '用户')]",
            "//input[contains(@id, 'username')]",
            "//input[contains(@name, 'username')]",
            "//input[contains(@class, 'username')]",
            "//input[contains(@class, 'account')]",
        ]

        username_input = None
        for selector in username_selectors:
            try:
                username_input = self.wait.until(EC.presence_of_element_located((By.XPATH, selector)))
                self.logger.info(f"找到用户名输入框: {selector}")
                break
            except Exception as e:
                continue

        if not username_input:
            self.logger.warning("未找到用户名输入框")
            return False

        username_input.clear()
        username_input.send_keys(username)
        self.logger.info(f"已输入用户名: {username}")
        self.smart_wait(1)

        # 查找密码输入框
        password_selectors = [
            "//input[@type='password']",
            "//input[@placeholder='密码']",
            "//input[contains(@placeholder, '密码')]",
            "//input[contains(@id, 'password')]",
            "//input[contains(@name, 'password')]",
            "//input[contains(@class, 'password')]",
        ]

        password_input = None
        for selector in password_selectors:
            try:
                password_input = self.wait.until(EC.presence_of_element_located((By.XPATH, selector)))
                self.logger.info(f"找到密码输入框: {selector}")
                break
            except Exception as e:
                continue

        if not password_input:
            self.logger.warning("未找到密码输入框")
            return False

        password_input.clear()
        password_input.send_keys(password)
        self.logger.info("已输入密码")
        self.smart_wait(1)

        # 查找登录按钮
        login_selectors = [
            "//button[contains(text(), '登录')]",
            "//button[contains(text(), '登 录')]",
            "//a[contains(text(), '登录')]",
            "//span[contains(text(), '登录')]",
            "//div[contains(text(), '登录')]",
            "//button[contains(@class, 'login')]",
            "//button[@type='submit']",
            "//input[@type='submit']",
            "//div[contains(@class, 'login-btn')]",
            "//div[contains(@class, 'loginBtn')]",
            "//span[contains(text(), '登录')]/parent::button",
            "//span[contains(text(), '登录')]/parent::div",
            "//span[contains(text(), '登录')]/parent::a",
            # 尝试查找所有可能的按钮
            "//button",
            "//div[@role='button']",
        ]

        login_btn = None
        for selector in login_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                for elem in elements:
                    try:
                        # 检查元素文本是否包含“登录”
                        if '登录' in elem.text or 'login' in elem.text.lower():
                            login_btn = elem
                            self.logger.info(f"找到登录按钮: {selector}, 文本: {elem.text}")
                            break
                    except:
                        continue
                if login_btn:
                    break
            except Exception as e:
                continue

        if not login_btn:
            self.logger.warning("未找到登录按钮")
            return False

        try:
            login_btn.click()
            self.logger.info("已点击登录按钮")
        except Exception as e:
            self.logger.warning(f"点击登录按钮失败，尝试ActionChains点击: {e}")
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                actions = ActionChains(self.driver)
                actions.move_to_element(login_btn)
                actions.click()
                actions.perform()
                self.logger.info("已通过ActionChains点击登录按钮")
            except Exception as e2:
                self.logger.error(f"ActionChains点击也失败: {e2}")
                return False
        
        self.smart_wait(3)
        return True

    def login_method2(self, username, password):
        """备用登录方式"""
        # 尝试通过JavaScript执行登录
        script = f"""
        var usernameInputs = document.querySelectorAll('input[type="text"], input[placeholder*="手机"], input[id*="username"]');
        var passwordInputs = document.querySelectorAll('input[type="password"], input[placeholder*="密码"], input[id*="password"]');
        var loginButtons = document.querySelectorAll('button[class*="login"], button:contains("登录"), input[type="submit"]');

        if (usernameInputs.length > 0 && passwordInputs.length > 0) {{
            usernameInputs[0].value = '{username}';
            passwordInputs[0].value = '{password}';
            return loginButtons.length > 0;
        }}
        return false;
        """

        result = self.driver.execute_script(script)
        if result:
            # 找到输入框和按钮，使用ActionChains模拟真实点击
            try:
                login_btn = self.driver.find_element(By.XPATH, "//button[contains(text(), '登录')] | //button[@type='submit'] | //input[@type='submit']")
                from selenium.webdriver.common.action_chains import ActionChains
                actions = ActionChains(self.driver)
                actions.move_to_element(login_btn)
                actions.click()
                actions.perform()
                self.logger.info("已通过ActionChains点击登录按钮")
                return True
            except Exception as e:
                self.logger.error(f"ActionChains点击登录按钮失败: {e}")
                return False
        return False
    
    def check_captcha(self):
        """检查是否有人机验证"""
        try:
            captcha_indicators = [
                "验证",
                "captcha",
                "人机",
                "滑动",
                "拼图",
                "安全验证",
                "verify",
                "安全检测"
            ]

            page_source = self.driver.page_source
            return any(indicator in page_source for indicator in captcha_indicators)
        except Exception as e:
            self.logger.error(f"检查验证码时出错: {e}")
            return False

    def wait_for_captcha_completion(self, timeout=60):
        """等待用户完成人机验证"""
        self.logger.info("检测到人机验证，请手动完成验证...")
        
        # 硬等待20秒，但每2秒检查一次是否已完成
        self.logger.info("⏳ 等待20秒，期间每2秒检查一次验证状态...")
        for i in range(10):  # 20秒分成10次，每次2秒
            time.sleep(2)
            
            # 检查是否已登录（验证通过）
            if self.check_login_success():
                self.logger.info("✅ 登录成功，立即继续执行")
                return True
            
            # 检查是否还有人机验证
            if not self.check_captcha():
                self.logger.info("✅ 人机验证已消失，立即继续执行")
                return True
        
        # 20秒后，开始正常的循环检查
        self.logger.info("⏰ 20秒已过，开始正常检查流程...")
        start_time = time.time()
        check_interval = 5  # 每5秒检查一次

        while time.time() - start_time < timeout:
            # 检查是否还有人机验证
            if not self.check_captcha():
                self.logger.info("人机验证已完成，继续执行程序")
                return True

            # 检查是否已登录（验证通过）
            if self.check_login_success():
                self.logger.info("登录成功，继续执行程序")
                return True

            # 显示等待信息
            elapsed = int(time.time() - start_time)
            remaining = int(timeout - elapsed)
            self.logger.info(f"等待人机验证完成... 已等待 {elapsed} 秒，剩余 {remaining} 秒")

            time.sleep(check_interval)

        self.logger.error("人机验证等待超时")
        return False

    def check_login_success(self):
        """检查是否登录成功"""
        try:
            # 检查是否在课程页面或主页
            current_url = self.driver.current_url
            if "onlinestuh5" in current_url and "login" not in current_url:
                return True

            # 检查页面内容
            page_source = self.driver.page_source
            if "我的课程" in page_source or "课程列表" in page_source:
                return True

            return False
        except Exception as e:
            self.logger.error(f"检查登录状态时出错: {e}")
            return False
    
    def find_course(self, course_name=None):
        """查找并点击课程（自动适配新版/老版布局）"""
        # 如果配置了使用侧边栏布局，则使用新版查找逻辑
        use_sidebar = self.account_config.get('use_sidebar_layout', False)
        
        if use_sidebar:
            self.logger.info("🆕 检测到配置为新版布局，使用侧边栏查找逻辑")
            # 【第一级】共享课标签页查找（严格+宽松）
            result = self.find_course_in_sidebar(course_name)
            if result:
                return True
            else:
                self.logger.warning("⚠️  共享课中未找到课程，切换到全界面查找")
                self.logger.info("🔍 第二级：尝试全界面查找模式")
                # 【第二级】全界面查找（有题目版本逻辑）
                result = self.find_course_legacy(course_name)
                if result:
                    return True
                else:
                    self.logger.warning("⚠️  全界面查找也失败，切换到最简化查找逻辑")
                    self.logger.info("🔍 第三级：使用无题目版本查找逻辑（兑底）")
                    # 【第三级】无题目版本查找逻辑（最简化，但仍进入有题目课程）
                    return self.find_course_simple(course_name)
        else:
            self.logger.info("📜 使用老版主区域查找逻辑")
            result = self.find_course_legacy(course_name)
            if result:
                return True
            else:
                self.logger.warning("⚠️  老版逻辑失败，切换到最简化查找逻辑")
                self.logger.info("🔍 使用无题目版本查找逻辑（兑底）")
                return self.find_course_simple(course_name)
    
    def find_course_in_sidebar(self, course_name=None):
        """新版布局：在“共享课”标签页中查找课程（根据要求.txt实现）"""
        if course_name is None:
            course_name = self.account_config.get('course_name')
        
        self.logger.info(f"正在在新版布局中查找'{course_name}'课程...")
        
        try:
            # 步骤1：确保页面已加载
            current_url = self.driver.current_url
            self.logger.info(f"当前页面URL: {current_url}")
            
            if '/onlinestuh5' not in current_url:
                self.logger.warning("当前不在主页，尝试导航...")
                self.driver.get('https://onlineweb.zhihuishu.com/onlinestuh5')
                self.smart_wait(5)
            
            # 步骤2：定位并激活“共享课”标签
            self.logger.info("步骤1: 查找并激活'共享课'标签...")
            
            # 多种标签页选择器
            tab_selectors = [
                "//div[contains(@class, 'tab')]//text()[normalize-space()='共享课']/ancestor::*[self::button or self::div or self::a][1]",
                "//button[normalize-space(text())='共享课']",
                "//div[contains(@class, 'tab')][normalize-space(text())='共享课']",
                "//a[normalize-space(text())='共享课']",
                "//*[@role='tab'][normalize-space(text())='共享课']",
                "//*[contains(text(), '共享课')]"
            ]
            
            shared_tab = None
            for tab_selector in tab_selectors:
                try:
                    tabs = self.driver.find_elements(By.XPATH, tab_selector)
                    # 过滤出可见且可交互的元素
                    for tab in tabs:
                        try:
                            if tab.is_displayed() and tab.is_enabled():
                                # 检查元素尺寸（确保不是0x0的隐藏元素）
                                size = tab.size
                                if size['width'] > 0 and size['height'] > 0:
                                    shared_tab = tab
                                    self.logger.info(f"✅ 找到'共享课'标签: {tab_selector}")
                                    break
                        except:
                            continue
                    if shared_tab:
                        break
                except Exception as e:
                    self.logger.debug(f"选择器失败 {tab_selector}: {e}")
                    continue
            
            if not shared_tab:
                self.logger.error("❌ 未找到'共享课'标签，可能不是新版布局")
                return False
            
            # 检查是否已激活
            tab_class = shared_tab.get_attribute('class') or ''
            tab_aria = shared_tab.get_attribute('aria-selected') or ''
            is_active = 'active' in tab_class.lower() or tab_aria == 'true'
            
            if not is_active:
                self.logger.info("点击激活'共享课'标签...")
                try:
                    # 滚动到元素可见位置
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", shared_tab)
                    self.smart_wait(0.5)
                    shared_tab.click()
                    self.logger.info("✅ 点击成功")
                except Exception as e:
                    self.logger.warning(f"普通点击失败，尝试JavaScript点击: {e}")
                    try:
                        # 课程列表页的标签点击可以使用JS
                        self.driver.execute_script("arguments[0].click();", shared_tab)
                        self.logger.info("✅ JavaScript点击成功")
                    except Exception as e2:
                        self.logger.error(f"❌ 所有点击方式都失败: {e2}")
                        return False
                self.smart_wait(2)
            else:
                self.logger.info("✅ '共享课'标签已激活")
            
            # 步骤3：定位“共享课”内容区域
            self.logger.info("步骤2: 定位'共享课'内容区域...")
            
            # 尝试多种方法获取内容区域
            content_root = None
            
            # 方法1：通过aria-controls
            aria_controls = shared_tab.get_attribute('aria-controls')
            if aria_controls:
                try:
                    content_root = self.driver.find_element(By.ID, aria_controls)
                    self.logger.info(f"✅ 通过aria-controls找到内容区: #{aria_controls}")
                except:
                    pass
            
            # 方法2：通过常见选择器
            if not content_root:
                content_selectors = [
                    "//div[@id='sharedCoursesContent']",
                    "//div[contains(@class, 'course-list-shared')]",
                    "//div[contains(@class, 'tab-panel')]//div[contains(@class, 'course')]",
                    "//div[contains(@class, 'shared')]//div[contains(@class, 'course')]"
                ]
                
                for selector in content_selectors:
                    try:
                        roots = self.driver.find_elements(By.XPATH, selector)
                        if roots:
                            content_root = roots[0]
                            self.logger.info(f"✅ 找到内容区: {selector}")
                            break
                    except:
                        continue
            
            if not content_root:
                self.logger.warning("⚠️  未找到专门的内容区，将在整个页面中查找")
                content_root = self.driver.find_element(By.TAG_NAME, 'body')
            
            # 步骤4：在内容区中滚动加载并查找课程卡片
            self.logger.info(f"步骤3: 在'共享课'区域中查找'{course_name}'课程卡片...")
            
            # 等待内容加载
            self.smart_wait(3)
            
            # 滚动加载
            for scroll_attempt in range(5):
                self.logger.info(f"滚动加载第 {scroll_attempt + 1} 次...")
                self.driver.execute_script("arguments[0].scrollIntoView();", content_root)
                self.driver.execute_script("window.scrollBy(0, 500);")
                self.smart_wait(1)
                
                # 查找所有课程卡片 - 使用更广泛的选择器
                card_selectors = [
                    ".//div[contains(@class, 'course-card')]",
                    ".//div[contains(@class, 'courseCard')]",
                    ".//div[contains(@class, 'course-item')]",
                    ".//div[contains(@class, 'courseItem')]",
                    ".//li[contains(@class, 'course')]",
                    ".//div[contains(@class, 'card')]",
                    ".//div[contains(@class, 'item')]",  # 新增
                    ".//li",  # 新增：尝试所有li元素
                    ".//div[.//*[contains(@class, 'img')]]",  # 新增：包含图片的div
                ]
                
                all_cards = []
                for card_selector in card_selectors:
                    try:
                        cards = content_root.find_elements(By.XPATH, card_selector)
                        if cards:
                            self.logger.debug(f"选择器 {card_selector} 找到 {len(cards)} 个元素")
                            all_cards.extend(cards)
                    except Exception as e:
                        self.logger.debug(f"选择器 {card_selector} 失败: {e}")
                        continue
                
                # 去重
                unique_cards = []
                seen_ids = set()
                for card in all_cards:
                    card_id = id(card)
                    if card_id not in seen_ids:
                        unique_cards.append(card)
                        seen_ids.add(card_id)
                
                if not unique_cards:
                    self.logger.warning("未找到任何课程卡片，继续滚动...")
                    # 调试：输出页面HTML
                    if scroll_attempt == 2:  # 第3次尝试时输出调试信息
                        try:
                            page_html = content_root.get_attribute('innerHTML')[:500]
                            self.logger.debug(f"内容区HTML片段: {page_html}")
                        except:
                            pass
                    continue
                
                self.logger.info(f"找到 {len(unique_cards)} 个课程卡片，开始精确匹配...")
                
                # 【增强调试】输出所有卡片的文本
                self.logger.info("-" * 50)
                self.logger.info("📝 所有课程卡片列表：")
                for idx, card in enumerate(unique_cards, 1):
                    try:
                        card_text = card.text or ''
                        self.logger.info(f"  [{idx}] {card_text[:100]}")
                    except Exception:
                        self.logger.info(f"  [{idx}] (无法读取文本)")
                self.logger.info("-" * 50)
                
                # 【分级查找策略】先严格匹配（6个条件），失败后宽松匹配（3个条件）
                matched_card = None
                
                # 【第一轮】严格匹配：6个条件
                self.logger.info("🔍 第一轮：严格匹配（6个条件）")
                for idx, card in enumerate(unique_cards, 1):
                    try:
                        card_text = card.text or ''
                        
                        # 条件1：课程名匹配
                        if course_name not in card_text:
                            continue
                        
                        # 条件2：排除重要提醒区域
                        card_classes = card.get_attribute('class') or ''
                        card_id = card.get_attribute('id') or ''
                        if 'important' in card_classes.lower() or 'reminder' in card_classes.lower() or 'carousel' in card_classes.lower():
                            self.logger.debug(f"⚠️  跳过重要提醒区卡片: {card_id}")
                            continue
                        
                        # 条件3：排除书名号和直播课
                        if '《' in card_text or '》' in card_text:
                            self.logger.debug(f"⚠️  排除书名号: {card_text[:40]}")
                            continue
                        if '直播' in card_text or '见面课' in card_text:
                            self.logger.debug(f"⚠️  排除直播课: {card_text[:40]}")
                            continue
                        
                        # 条件4：必须有进度信息
                        import re
                        progress_match = re.search(r'进度\s*[:：]\s*(\d+(?:\.\d+)?)%', card_text)
                        if not progress_match:
                            self.logger.debug(f"⚠️  未找到进度信息: {card_text[:60]}")
                            continue
                        
                        progress_value = progress_match.group(1)
                        self.logger.info(f"✅ 找到进度: {progress_value}%")
                        
                        # 条件5：必须包含教师/机构白名单
                        teacher_keywords = ['吉林大学', '北京大学', '清华大学', '北京师范大学', '中山大学', '南京大学',
                                           '杨振斌', '李娜', '王芳', '张伟', '教授', '老师', '大学', '学院', '讲师']
                        
                        found_teacher = False
                        for keyword in teacher_keywords:
                            if keyword in card_text:
                                self.logger.info(f"✅ 找到教师/机构: {keyword}")
                                found_teacher = True
                                break
                        
                        if not found_teacher:
                            self.logger.debug(f"⚠️  未找到教师/机构: {card_text[:60]}")
                            continue
                        
                        # 条件6：必须有图片封面
                        has_image = len(card.find_elements(By.TAG_NAME, 'img')) > 0
                        if not has_image:
                            self.logger.debug(f"⚠️  未找到图片封面: {card_text[:60]}")
                            continue
                        
                        self.logger.info("✅ 卡片包含图片封面")
                        
                        # 所有6个条件匹配
                        self.logger.info(f"🎯 严格匹配成功！找到课程卡片 #{idx}: {card_text[:80]}")
                        matched_card = (card, idx, card_text)
                        break
                    
                    except Exception as card_error:
                        self.logger.debug(f"处理卡片 #{idx} 时出错: {card_error}")
                        continue
                
                # 【第二轮】如果严格匹配失败，使用宽松匹配：3个条件
                if not matched_card:
                    self.logger.warning("⚠️  严格匹配失败，切换到宽松匹配模式")
                    self.logger.info("🔍 第二轮：宽松匹配（3个条件）")
                    
                    for idx, card in enumerate(unique_cards, 1):
                        try:
                            card_text = card.text or ''
                            
                            # 条件1：课程名匹配
                            if course_name not in card_text:
                                continue
                            
                            # 条件2：排除重要提醒区域
                            card_classes = card.get_attribute('class') or ''
                            card_id = card.get_attribute('id') or ''
                            if 'important' in card_classes.lower() or 'reminder' in card_classes.lower() or 'carousel' in card_classes.lower():
                                self.logger.debug(f"⚠️  跳过重要提醒区卡片: {card_id}")
                                continue
                            
                            # 条件3：排除书名号和直播课
                            if '《' in card_text or '》' in card_text:
                                self.logger.debug(f"⚠️  排除书名号: {card_text[:40]}")
                                continue
                            if '直播' in card_text or '见面课' in card_text:
                                self.logger.debug(f"⚠️  排除直播课: {card_text[:40]}")
                                continue
                            
                            # 宽松匹配成功！
                            self.logger.info(f"🎯 宽松匹配成功！找到课程卡片 #{idx}: {card_text[:80]}")
                            matched_card = (card, idx, card_text)
                            break
                        
                        except Exception as card_error:
                            self.logger.debug(f"处理卡片 #{idx} 时出错: {card_error}")
                            continue
                
                # 【点击匹配到的课程】
                if matched_card:
                    card, idx, card_text = matched_card
                    
                    # 滚动到可视区域
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", card)
                    self.smart_wait(1)
                    
                    # 尝试点击卡片内的链接
                    link = None
                    try:
                        link = card.find_element(By.XPATH, ".//a[contains(@href, 'course') or contains(@href, 'study')]")
                    except:
                        # 如果没有链接，尝试点击卡片本身
                        link = card
                    
                    # 多策略点击（在课程列表页可以使用JS）
                    try:
                        link.click()
                        self.logger.info("✅ 普通点击成功")
                    except:
                        try:
                            # 使用JavaScript点击（课程列表页不涉及视频播放器，可以用JS）
                            self.driver.execute_script("arguments[0].click();", link)
                            self.logger.info("✅ JavaScript点击成功")
                        except Exception as e:
                            self.logger.error(f"所有点击方式都失败: {e}")
                            # 继续下一次滚动尝试
                    
                    # 等待页面跳转
                    self.smart_wait(5)
                    
                    # 验证是否进入课程详情页
                    new_url = self.driver.current_url
                    if 'course' in new_url.lower() or 'detail' in new_url.lower() or 'study' in new_url.lower():
                        self.logger.info(f"✅ 成功进入课程页: {new_url}")
                        return True
                    else:
                        self.logger.warning(f"⚠️  URL未变化: {new_url}")
            
            self.logger.error(f"未找到符合所有条件的'{course_name}'课程卡片")
            return False
            
        except Exception as e:
            self.logger.error(f"新版布局查找课程失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def find_course_legacy(self, course_name=None):
        """查找并点击课程（结合v4.10和原版本的改进逻辑）"""
        # 如果没有传入课程名称，从配置文件读取
        if course_name is None:
            course_name = self.account_config.get('course_name')
        
        self.logger.info(f"正在查找'{course_name}'课程...")
        
        # 检查浏览器是否还在运行
        try:
            current_url = self.driver.current_url
            self.logger.info(f"当前页面URL: {current_url}")
        except Exception as e:
            self.logger.error("⚠️  浏览器已关闭！请不要手动关闭浏览器窗口！")
            self.logger.error(f"错误详情: {e}")
            return False
        
        # 先尝试滚动页面，确保所有课程都加载出来
        self.logger.info("滚动页面加载所有课程...")
        for i in range(3):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            self.smart_wait(1)
            self.driver.execute_script("window.scrollTo(0, 0);")
            self.smart_wait(1)

        # 改进的多种课程选择器（优先查找<a>标签）
        course_selectors = [
            # 策略1：优先查找<a>标签链接（最可靠）
            f"//a[contains(text(), '{course_name}')]",
            # 策略2：查找课程卡片内的<a>标签
            f"//div[contains(@class, 'course')]//a[contains(., '{course_name}')]",
            f"//div[contains(@class, 'card')]//a[contains(., '{course_name}')]",
            # 策略3：通过作者信息查找课程（新增）
            f"//div[contains(., '{course_name}') and (contains(., '杨振斌') or contains(., '吉林大学'))]",
            f"//*[contains(., '杨振斌') and contains(., '吉林大学')]",
            # 策略4：查找课程卡片（整个卡片可能可点击）
            f"//div[contains(@class, 'course-item') or contains(@class, 'courseItem')][contains(., '{course_name}')]",
            f"//div[contains(@class, 'course-card') or contains(@class, 'courseCard')][contains(., '{course_name}')]",
            # 策略5：查找其他可能的链接容器
            f"//h3[contains(text(), '{course_name}')]",
            f"//h4[contains(text(), '{course_name}')]",
            # 策略6：更广泛的查找
            f"//*[contains(text(), '{course_name}')]",
        ]
        
        # 尝试每个选择器
        for selector_idx, selector in enumerate(course_selectors, 1):
            try:
                self.logger.info(f"尝试策略{selector_idx}: {selector[:80]}...")
                
                # 查找所有匹配的元素
                elements = self.driver.find_elements(By.XPATH, selector)
                
                if not elements:
                    self.logger.info(f"策略{selector_idx}未找到元素")
                    continue
                
                self.logger.info(f"策略{selector_idx}找到 {len(elements)} 个原始元素")
                
                # 【改进1】过滤掉包含书名号和直播的元素（严格模式）
                filtered_elements = []
                for elem in elements:
                    try:
                        elem_text = elem.text or ''
                        
                        # 【严格过滤】排除包含书名号的元素（《》）
                        if '《' in elem_text or '》' in elem_text:
                            self.logger.debug(f"⚠️  排除书名号: {elem_text[:40]}")
                            continue
                        
                        # 【严格过滤】排除直播课和见面课
                        if '直播' in elem_text or '见面课' in elem_text:
                            self.logger.debug(f"⚠️  排除直播课: {elem_text[:40]}")
                            continue
                        
                        # 【严格过滤】必须包含课程名
                        if course_name in elem_text:
                            filtered_elements.append(elem)
                        else:
                            self.logger.debug(f"⚠️  不包含课程名: {elem_text[:40]}")
                    except:
                        continue
                
                self.logger.info(f"过滤后剩余 {len(filtered_elements)} 个元素")
                
                if not filtered_elements:
                    continue
                
                # 【改进2】优先尝试<a>标签，然后尝试查找内部<a>标签
                for idx, element in enumerate(filtered_elements):
                    try:
                        elem_text = element.text[:50] if element.text else "(无文本)"
                        elem_tag = element.tag_name
                        self.logger.info(f"\n尝试点击元素 {idx+1}/{len(filtered_elements)}: <{elem_tag}> {elem_text}")
                        
                        # 滚动到元素
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                        self.smart_wait(1)
                        
                        # 【改进3】如果是<a>标签，验证href后直接点击
                        if elem_tag.lower() == 'a':
                            elem_href = element.get_attribute('href') or ''
                            self.logger.debug(f"<a>标签 href: {elem_href}")
                            
                            # 验证href是否有效（包含课程相关路径）
                            if elem_href and ('studycenter' in elem_href or 'course' in elem_href or 'learning' in elem_href):
                                self.logger.info("✅ 这是有效的课程链接")
                                
                                # 【改进4】多策略点击：普通点击 → JavaScript点击（课程列表页可以用JS）
                                try:
                                    self.logger.debug("尝试普通点击...")
                                    element.click()
                                    self.logger.info("✅ 普通点击成功")
                                    self.smart_wait(5)
                                    return True
                                except Exception as click_err:
                                    self.logger.debug(f"普通点击失败: {click_err}，尝试JavaScript点击...")
                                    try:
                                        self.driver.execute_script("arguments[0].click();", element)
                                        self.logger.info("✅ JavaScript点击成功")
                                        self.smart_wait(5)
                                        return True
                                    except Exception as ac_err:
                                        self.logger.warning(f"ActionChains点击也失败: {ac_err}")
                                        continue
                            else:
                                self.logger.debug(f"⚠️  <a>标签但href无效: {elem_href}")
                                continue
                        
                        # 【改进5】如果不是<a>标签，查找内部的<a>标签
                        else:
                            self.logger.debug(f"非<a>标签，查找内部链接...")
                            try:
                                # 在当前元素内部查找<a>标签
                                inner_links = element.find_elements(By.XPATH, ".//a")
                                if inner_links:
                                    self.logger.debug(f"找到 {len(inner_links)} 个内部<a>标签")
                                    
                                    for inner_link in inner_links:
                                        inner_href = inner_link.get_attribute('href') or ''
                                        inner_text = inner_link.text or ''
                                        
                                        self.logger.debug(f"检查内部链接: {inner_text[:40]}, href={inner_href[:60]}")
                                        
                                        # 验证内部链接href是否有效
                                        if inner_href and ('studycenter' in inner_href or 'course' in inner_href or 'learning' in inner_href):
                                            # 【严格过滤】排除包含书名号、直播和见面课的链接
                                            if '《' in inner_text or '》' in inner_text:
                                                self.logger.debug(f"⚠️  内部链接包含书名号: {inner_text[:40]}")
                                                continue
                                            if '直播' in inner_text or '见面课' in inner_text:
                                                self.logger.debug(f"⚠️  内部链接是直播课: {inner_text[:40]}")
                                                continue
                                            
                                            self.logger.info(f"✅ 找到有效的内部链接: {inner_text[:40] if inner_text else '(无文本)'}, href={inner_href[:60]}")
                                            
                                            # 多策略点击内部链接
                                            try:
                                                inner_link.click()
                                                self.logger.info("✅ 内部链接普通点击成功")
                                                self.smart_wait(5)
                                                return True
                                            except:
                                                try:
                                                    from selenium.webdriver.common.action_chains import ActionChains
                                                    actions = ActionChains(self.driver)
                                                    actions.move_to_element(inner_link)
                                                    actions.click()
                                                    actions.perform()
                                                    self.logger.info("✅ 内部链接ActionChains点击成功")
                                                    self.smart_wait(5)
                                                    return True
                                                except Exception as e:
                                                    self.logger.warning(f"内部链接点击失败: {e}")
                                                    continue
                                        else:
                                            self.logger.debug(f"⚠️  内部链接href无效: {inner_href[:60]}")
                                else:
                                    self.logger.debug("未找到内部<a>标签")
                            except Exception as e:
                                self.logger.debug(f"查找内部链接失败: {e}")
                    
                    except Exception as elem_err:
                        self.logger.warning(f"处理元素 {idx+1} 时出错: {elem_err}")
                        continue

            except Exception as e:
                self.logger.warning(f"策略{selector_idx}失败: {e}")
                continue

        self.logger.error(f"未找到'{course_name}'课程")
        self.logger.error("请检查：")
        self.logger.error("1. 课程名称是否正确（当前配置：'" + course_name + "'）")
        self.logger.error("2. 是否需要先点击某个标签页（如'共享课'）")
        return False
    
    def find_course_simple(self, course_name=None):
        """最简化查找逻辑（复制无题目版本，作为最后兜底）"""
        if course_name is None:
            course_name = self.account_config.get('course_name')
        
        self.logger.info(f"🔍 【最简化查找】'{course_name}'课程...")
        self.logger.info("💡 使用无题目版本逻辑（保证可运行的最低级版本）")
        
        # 检查浏览器是否还在运行
        try:
            current_url = self.driver.current_url
            self.logger.info(f"当前页面URL: {current_url}")
        except Exception as e:
            self.logger.error("⚠️  浏览器已关闭！请不要手动关闭浏览器窗口！")
            self.logger.error(f"错误详情: {e}")
            return False
        
        # 先尝试滚动页面，确保所有课程都加载出来
        self.logger.info("滚动页面加载所有课程...")
        for i in range(3):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            self.smart_wait(1)
            self.driver.execute_script("window.scrollTo(0, 0);")
            self.smart_wait(1)

        # 多种课程选择器（无题目版本的逻辑）
        course_selectors = [
            # 直接查找文本
            f"//*[contains(text(), '{course_name}')]",
            f"//div[contains(text(), '{course_name}')]",
            f"//a[contains(text(), '{course_name}')]",
            f"//span[contains(text(), '{course_name}')]",
            f"//h3[contains(text(), '{course_name}')]",
            f"//h4[contains(text(), '{course_name}')]",
            f"//p[contains(text(), '{course_name}')]",
            # 查找课程卡片
            f"//div[contains(@class, 'course')]//*[contains(text(), '{course_name}')]",
            f"//div[contains(@class, 'card')]//*[contains(text(), '{course_name}')]",
        ]
        
        # 尝试每个选择器
        for selector_idx, selector in enumerate(course_selectors, 1):
            try:
                self.logger.info(f"尝试最简选择器 {selector_idx}/{len(course_selectors)}: {selector[:80]}...")
                
                # 查找所有匹配的元素
                elements = self.driver.find_elements(By.XPATH, selector)
                
                if not elements:
                    self.logger.info(f"选择器 {selector_idx} 未找到元素")
                    continue
                
                self.logger.info(f"选择器 {selector_idx} 找到 {len(elements)} 个匹配的元素")
                
                # 尝试点击每个匹配的元素
                for idx, element in enumerate(elements):
                    try:
                        elem_text = element.text[:50] if element.text else "(无文本)"
                        self.logger.info(f"尝试元素 {idx+1}/{len(elements)}: {elem_text}")
                        
                        # 滚动到元素
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                        self.smart_wait(1)
                        
                        # 尝试点击
                        try:
                            element.click()
                            self.logger.info(f"✅ 成功点击'{course_name}'课程")
                            self.smart_wait(5)
                            return True
                        except Exception as click_err:
                            # 如果常规点击失败，尝试 ActionChains 点击
                            self.logger.info(f"常规点击失败，尝试ActionChains点击")
                            try:
                                from selenium.webdriver.common.action_chains import ActionChains
                                actions = ActionChains(self.driver)
                                actions.move_to_element(element)
                                actions.click()
                                actions.perform()
                                self.logger.info(f"✅ 通过ActionChains成功点击'{course_name}'课程")
                                self.smart_wait(5)
                                return True
                            except Exception as ac_err:
                                self.logger.warning(f"ActionChains点击也失败: {ac_err}")
                                continue
                    
                    except Exception as elem_err:
                        self.logger.warning(f"处理元素 {idx+1} 时出错: {elem_err}")
                        continue

            except Exception as e:
                self.logger.warning(f"选择器 {selector_idx} 失败: {e}")
                continue

        self.logger.error(f"❌ 最简化查找也未找到'{course_name}'课程")
        self.logger.error("请检查：")
        self.logger.error("1. 课程名称是否正确（当前配置：'" + course_name + "'）")
        self.logger.error("2. 课程是否确实存在于当前页面")
        return False
    
    def enter_study_page(self):
        """进入学习页面"""
        self.logger.info("进入学习页面...")
        
        try:
            # 切换到新窗口（课程详情）
            if len(self.driver.window_handles) > 1:
                self.driver.switch_to.window(self.driver.window_handles[-1])
            
            self.smart_wait(3)
            
            # 点击"继续学习"或"开始学习"按钮
            try:
                continue_button = self.driver.find_element(By.XPATH, "//*[contains(text(), '继续学习') or contains(text(), '开始学习')]")
                continue_button.click()
                self.logger.info("✅ 已点击继续学习")
                self.smart_wait(5)
            except:
                self.logger.info("未找到继续学习按钮，可能已在学习页面")
            
            # 切换到学习窗口
            if len(self.driver.window_handles) > 1:
                self.driver.switch_to.window(self.driver.window_handles[-1])
            
            self.smart_wait(3)
            self.logger.info(f"✅ 当前页面: {self.driver.current_url}")
            
            # 关闭所有弹窗（学前必读、AI助手等）
            self.close_all_dialogs()
            
            return True
            
        except Exception as e:
            self.logger.error(f"进入学习页面失败: {e}")
            return False
    
    def find_unwatched_videos(self):
        """查找未观看的视频（从右侧目录），同时记录已观看视频列表"""
        self.logger.info("🔍 查找未观看的视频...")
        unwatched_videos = []
        watched_videos = []  # 本次检索发现的已观看视频
        
        # 如果已有已观看列表，先加载（累积模式）
        if hasattr(self, 'watched_video_list') and self.watched_video_list:
            watched_videos = self.watched_video_list.copy()  # 复制现有列表
            self.logger.debug(f"📚 加载现有已观看视频列表: {len(watched_videos)} 个")
        
        try:
            # 查找右侧目录侧边栏
            sidebar_selectors = [
                "//div[contains(@class, 'box-right')]",  # 优先：右侧整个目录容器
                "//div[contains(@class, 'catalog_box')]",  # 目录盒子
                "//div[contains(@class, 'catalog')]",
                "//div[contains(@class, 'sidebar')]",
                "//div[contains(@class, 'directory')]",
                "//aside",
            ]
            
            sidebar = None
            for selector in sidebar_selectors:
                try:
                    sidebar = self.driver.find_element(By.XPATH, selector)
                    if sidebar and sidebar.is_displayed():
                        self.logger.info(f"✅ 找到右侧目录: {selector}")
                        break
                except:
                    continue
            
            if not sidebar:
                self.logger.warning("⚠️  未找到右侧目录，可能不是新版布局")
                return []
            
            # 滚动侧边栏加载所有内容
            self.logger.info("📜 滚动右侧目录加载所有视频...")
            
            # 查找实际的滚动容器（el-scrollbar__wrap）
            scroll_container = None
            try:
                # 优先查找 el-scrollbar__wrap
                scroll_container = sidebar.find_element(By.XPATH, ".//*[contains(@class, 'el-scrollbar__wrap')]")
                self.logger.info("✅ 找到滚动容器: el-scrollbar__wrap")
            except:
                try:
                    # 备用：查找其他滚动容器
                    scroll_container = sidebar.find_element(By.XPATH, ".//*[contains(@class, 'scrollbar-wrap') or contains(@class, 'scroll-wrap')]")
                    self.logger.info("✅ 找到滚动容器: scrollbar-wrap")
                except:
                    # 最后使用sidebar本身
                    scroll_container = sidebar
                    self.logger.info("使用侧边栏本身作为滚动容器")
            
            # 使用鼠标滚轮事件模拟真实滚动
            self.logger.info("🔄 开始使用鼠标滚轮模拟滚动...")
            
            max_scroll_attempts = 20  # 最多滚动20次
            scroll_no_change_count = 0  # 连续未变化次数
            
            for i in range(max_scroll_attempts):
                # 记录滚动前的位置
                scroll_before = self.driver.execute_script("return arguments[0].scrollTop;", scroll_container)
                
                # 使用JavaScript触发wheel事件（模拟鼠标滚轮）
                self.driver.execute_script("""
                    var element = arguments[0];
                    var wheelEvent = new WheelEvent('wheel', {
                        deltaY: 500,  // 向下滚动500像素
                        bubbles: true,
                        cancelable: true
                    });
                    element.dispatchEvent(wheelEvent);
                    
                    // 备用方法：直接修改scrollTop
                    element.scrollTop = element.scrollTop + 500;
                """, scroll_container)
                
                self.smart_wait(0.8)  # 等待滚动动画和内容加载
                
                # 记录滚动后的位置
                scroll_after = self.driver.execute_script("return arguments[0].scrollTop;", scroll_container)
                scroll_height = self.driver.execute_script("return arguments[0].scrollHeight;", scroll_container)
                
                self.logger.info(f"  滚动 {i+1}/{max_scroll_attempts}: {scroll_before}px → {scroll_after}px (总高度: {scroll_height}px)")
                
                # 如果滚动位置没有变化
                if scroll_after == scroll_before:
                    scroll_no_change_count += 1
                    self.logger.debug(f"  ⚠️  滚动位置未变化 ({scroll_no_change_count}/3)")
                    
                    # 连续3次未变化，说明已经到底
                    if scroll_no_change_count >= 3:
                        self.logger.info(f"  ✅ 滚动位置连续3次未变化，已到达底部")
                        break
                else:
                    scroll_no_change_count = 0  # 重置计数
                
                # 如果已经到底，提前退出
                if scroll_after >= scroll_height - 100:
                    self.logger.info(f"  ✅ 已滚动到底部，提前结束滚动")
                    break
            
            self.logger.info("✅ 滚动完成，等待内容加载...")
            self.smart_wait(2)
            
            # 回到顶部
            self.driver.execute_script("arguments[0].scrollTop = 0;", scroll_container)
            self.smart_wait(1)
            
            # 在侧边栏中查找视频元素
            self.logger.info("🔍 开始查找视频元素...")
            
            video_selectors = [
                ".//li[contains(@class, 'clearfix')]",  # 优先：课程列表项
                ".//div[contains(@class, 'video') or contains(@class, 'lesson')]",
                ".//li[contains(@class, 'video') or contains(@class, 'lesson')]",
                ".//a[contains(@class, 'video') or contains(@class, 'lesson')]",
                ".//*[contains(@class, 'catalog_title')]",  # 课程标题
                ".//div[contains(@class, 'item')]",
                ".//div[contains(@class, 'chapter-item')]",
                ".//span[contains(@class, 'catalog_title')]",  # span标签的课程标题
                ".//li",  # 通用li元素
            ]
            
            all_video_elements = []
            for selector in video_selectors:
                try:
                    elements = sidebar.find_elements(By.XPATH, selector)
                    if elements:
                        self.logger.info(f"✅ 选择器 '{selector}' 找到 {len(elements)} 个元素")
                        all_video_elements.extend(elements)
                    else:
                        self.logger.debug(f"⚠️  选择器 '{selector}' 未找到元素")
                except Exception as e:
                    self.logger.debug(f"❌ 选择器 '{selector}' 失败: {e}")
            
            # 去重
            unique_elements = list(dict.fromkeys(all_video_elements))
            self.logger.info(f"📋 总共找到 {len(unique_elements)} 个去重后的视频元素")
            
            # 如果找不到任何元素，保存HTML调试
            if len(unique_elements) == 0:
                try:
                    debug_html = sidebar.get_attribute('outerHTML')
                    # 保存到log文件夹，避免污染根目录
                    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    debug_file = os.path.join(project_root, 'log', 'debug_sidebar.html')
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        f.write(debug_html)
                    self.logger.warning(f"⚠️  未找到任何视频元素，已保存侧边栏HTML到 {debug_file}")
                    self.logger.info("🔍 请检查 log/debug_sidebar.html 文件，查看实际的HTML结构")
                except Exception as e:
                    self.logger.debug(f"保存HTML失败: {e}")
            
            # 筛选未观看视频
            for idx, element in enumerate(unique_elements):
                try:
                    text = element.text
                    if not text or len(text) < 3:
                        continue
                    
                    # 跳过PPT文件
                    if '.pptx' in text.lower() or '.ppt' in text.lower():
                        self.logger.debug(f"  → 跳过：PPT文件 ({text[:30]}...)")
                        continue
                    
                    # 跳过PDF等其他文件
                    if '.pdf' in text.lower():
                        self.logger.debug(f"  → 跳过：PDF文件 ({text[:30]}...)")
                        continue

                    # 跳过作业
                    if "作业" in text:
                        self.logger.debug(f"  → 跳过：作业 ({text[:30]}...)")
                        continue
                    
                    # 跳过非视频内容（见面课、课程问答、课程表、成绩分析、课程资料、平时测试）
                    skip_keywords = ["见面课", "课程问答", "课程表", "成绩分析", "课程资料", "平时测试"]
                    if any(keyword in text for keyword in skip_keywords):
                        self.logger.debug(f"  → 跳过：非视频内容 ({text[:30]}...)")
                        continue
                    
                    # 跳过章节标题（只有章节名称，没有时长信息）
                    # 例如："绪章\n绪论——增强适应能力，争做创造性人才"
                    if ':' not in text and 'px' not in text:  # 没有时长格式
                        # 检查是否包含数字编号（如 0.1, 1.1, 2.1.1）
                        import re
                        # 匹配视频编号格式：至少一个数字 + 点 + 至少一个数字（可选再次重复）
                        # 0.1, 1.2.3, 2.1.6 等是视频
                        # 0.2, 1.1, 2.1 等可能是章节标题
                        has_valid_number = re.search(r'\d+\.\d+\.\d+', text)  # 三级编号（如 2.1.6）
                        
                        if not has_valid_number:
                            # 没有三级编号，检查是否是二级编号
                            has_two_level = re.search(r'\d+\.\d+', text)
                            
                            if has_two_level:
                                # 有二级编号但没有时长，检查是否是章节标题
                                # 如果编号中间没有空格且后面紧跟\n，可能是章节标题
                                # 例如："0.2\n大学生活..." 是章节标题
                                # 而："2.1.6\n调节情绪\n11%\n00:07:14" 是视频
                                match = re.search(r'^(\d+\.\d+)\s*\n', text)
                                if match:
                                    # 编号后直接换行，可能是章节标题
                                    self.logger.debug(f"  → 跳过：章节标题 ({text[:30]}...)")
                                    continue
                            else:
                                # 没有编号且没有时长，必定是章节标题
                                self.logger.debug(f"  → 跳过：章节标题 ({text[:30]}...)")
                                continue

                    # 检查是否已完成（查找蓝色勾选标记）
                    try:
                        # 方法1：查找 time_icofinish class（知到平台完成标记）
                        parent_element = element  # 从当前元素开始
                        
                        # 如果是span，向上查找父元素
                        try:
                            if element.tag_name == 'span':
                                parent_element = element.find_element(By.XPATH, "./..")
                        except:
                            pass
                        
                        # 查找完成标记（优先time_icofinish）
                        completed_markers = parent_element.find_elements(By.XPATH, 
                            ".//*[contains(@class, 'time_icofinish') or contains(@class, 'complete') or contains(@class, 'finish') or contains(@class, 'done') or contains(@class, '已完成')]")
                        
                        if completed_markers:
                            self.logger.debug(f"  → 跳过：找到完成标记 ({text[:30]}...)")
                            # 记录已观看视频（去重）
                            video_title = self._extract_video_title(text)
                            # 检查是否已存在
                            if not any(v.get('title') == video_title for v in watched_videos):
                                watched_videos.append({
                                    'text': text[:100],
                                    'title': video_title
                                })
                                self.logger.debug(f"  ✅ 添加到已观看列表: {video_title[:30]}")
                            continue
                        
                        # 方法2：检查进度是否100%
                        try:
                            progress_element = parent_element.find_element(By.XPATH, ".//*[contains(@class, 'progress-num')]")
                            progress_text = progress_element.text.strip()
                            # 提取数字
                            import re
                            progress_match = re.search(r'(\d+)%', progress_text)
                            if progress_match:
                                progress_value = int(progress_match.group(1))
                                if progress_value == 100:
                                    self.logger.debug(f"  → 跳过：进度100% ({text[:30]}...)")
                                    # 记录已观看视频（去重）
                                    video_title = self._extract_video_title(text)
                                    if not any(v.get('title') == video_title for v in watched_videos):
                                        watched_videos.append({
                                            'text': text[:100],
                                            'title': video_title
                                        })
                                        self.logger.debug(f"  ✅ 添加到已观看列表: {video_title[:30]}")
                                    continue
                                elif progress_value > 0:
                                    # 有进度但未完成，记录进度
                                    self.logger.debug(f"  ℹ️  进度{progress_value}%: {text[:30]}...")
                        except:
                            pass
                        
                        # 方法3：检查文本中是否包含100%或完成关键词
                        if '100%' in text or '已完成' in text or '已学完' in text:
                            self.logger.debug(f"  → 跳过：文本包含完成标记 ({text[:30]}...)")
                            # 记录已观看视频（去重）
                            video_title = self._extract_video_title(text)
                            if not any(v.get('title') == video_title for v in watched_videos):
                                watched_videos.append({
                                    'text': text[:100],
                                    'title': video_title
                                })
                                self.logger.debug(f"  ✅ 添加到已观看列表: {video_title[:30]}")
                            continue
                            
                    except Exception as e:
                        self.logger.debug(f"  检查完成状态失败: {e}")
                        pass

                    # 尝试判断是否是视频
                    if element.is_displayed() and element.is_enabled():
                        unwatched_videos.append({
                            'element': element,
                            'text': text[:100]
                        })
                        self.logger.info(f"  → ✅ 找到未观看视频: {text[:50]}...")
                        
                except Exception as e:
                    self.logger.debug(f"处理视频元素 {idx+1} 时出错: {e}")
                    continue
            
            self.logger.info(f"\n🎯 共找到 {len(unwatched_videos)} 个未观看视频")
            self.logger.info(f"📚 共找到 {len(watched_videos)} 个已观看视频")
            
            # 保存已观看视频列表为类属性，供后续检查使用
            self.watched_video_list = watched_videos
            self.logger.debug(f"已保存已观看视频列表: {len(watched_videos)} 个")
            
            return unwatched_videos
            
        except Exception as e:
            self.logger.error(f"查找视频时出错: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []
    
    def _extract_video_title(self, text):
        """从元素文本中提取视频标题（去除进度、时长等信息）"""
        import re
        # 移除进度百分比（如 11%, 100%）
        text = re.sub(r'\d+%', '', text)
        # 移除时长（如 00:07:14）
        text = re.sub(r'\d{2}:\d{2}:\d{2}', '', text)
        text = re.sub(r'\d{2}:\d{2}', '', text)
        # 移除多余的空格和换行
        text = ' '.join(text.split())
        # 取前50个字符作为标题
        return text[:50].strip()
    
    def get_current_video_title(self):
        """获取当前正在播放的视频标题（从左上角）"""
        try:
            # 尝试多种选择器查找视频标题
            title_selectors = [
                "//span[@class='lesson-order_videotop_lesson']",  # 知到平台常见
                "//div[contains(@class, 'video-title')]",
                "//div[contains(@class, 'videotop')]//span",
                "//h1[contains(@class, 'title')]",
                "//div[contains(@class, 'current-video')]//span",
            ]
            
            for selector in title_selectors:
                try:
                    element = self.driver.find_element(By.XPATH, selector)
                    if element and element.is_displayed():
                        title = element.text.strip()
                        if title:
                            self.logger.debug(f"获取到当前视频标题: {title[:50]}")
                            return self._extract_video_title(title)
                except:
                    continue
            
            self.logger.debug("未找到当前视频标题元素")
            return None
        except Exception as e:
            self.logger.debug(f"获取当前视频标题失败: {e}")
            return None
    
    def check_and_skip_watched_video(self):
        """检查当前播放的视频是否已观看，如果是则跳转到下一个未观看视频"""
        try:
            # 如果没有已观看视频列表，直接返回
            if not hasattr(self, 'watched_video_list') or not self.watched_video_list:
                return False
            
            # 获取当前播放的视频标题
            current_title = self.get_current_video_title()
            if not current_title:
                return False
            
            # 检查是否在已观看列表中
            for watched in self.watched_video_list:
                watched_title = watched.get('title', '')
                # 使用模糊匹配（包含关系）
                if watched_title and (watched_title in current_title or current_title in watched_title):
                    self.logger.warning(f"⚠️  检测到重复播放已观看视频: {current_title}")
                    self.logger.info("🔄 重新检索视频列表，跳转到下一个未观看视频...")
                    
                    # 重新查找未观看视频
                    unwatched_videos = self.find_unwatched_videos()
                    
                    if not unwatched_videos:
                        self.logger.warning("⚠️  未找到未观看视频，继续监控")
                        return False
                    
                    # 点击第一个未观看视频
                    first_video = unwatched_videos[0]
                    self.logger.info(f"🎬 点击播放: {first_video['text'][:50]}")
                    
                    try:
                        first_video['element'].click()
                        self.logger.info("✅ 普通点击成功")
                    except:
                        try:
                            from selenium.webdriver.common.action_chains import ActionChains
                            actions = ActionChains(self.driver)
                            actions.move_to_element(first_video['element'])
                            actions.click()
                            actions.perform()
                            self.logger.info("✅ ActionChains点击成功")
                        except Exception as e:
                            self.logger.error(f"❌ 点击视频失败: {e}")
                    
                    self.smart_wait(3)
                    
                    # 【改进】点击视频中央区域启动播放（模拟真实点击+随机偏移）
                    try:
                        video_element = self.driver.find_element(By.TAG_NAME, 'video')
                        if video_element:
                            # 获取视频元素的位置和大小
                            location = video_element.location
                            size = video_element.size
                            
                            # 计算中心点
                            center_x = location['x'] + size['width'] // 2
                            center_y = location['y'] + size['height'] // 2
                            
                            # 添加随机偏移（±50像素）
                            import random
                            offset_x = random.randint(-50, 50)
                            offset_y = random.randint(-50, 50)
                            
                            self.logger.info(f"📍 视频中心: ({center_x}, {center_y}), 偏移: ({offset_x:+d}, {offset_y:+d})")
                            
                            # 使用ActionChains点击指定坐标
                            from selenium.webdriver.common.action_chains import ActionChains
                            actions = ActionChains(self.driver)
                            actions.move_to_element_with_offset(video_element, offset_x, offset_y)
                            actions.click()
                            actions.perform()
                            
                            self.logger.info("✅ 已点击视频启动播放（含随机偏移）")
                        else:
                            self.logger.warning("⚠️  未找到video元素")
                    except Exception as e:
                        self.logger.warning(f"⚠️  点击视频失败: {e}")
                    
                    self.smart_wait(2)
                    return True
            
            return False
        except Exception as e:
            self.logger.error(f"检查重复播放时出错: {e}")
            return False
    
    def close_all_dialogs(self):
        """关闭所有弹窗（学前必读、AI助手等）"""
        self.logger.info("🚨 检查并关闭弹窗...")
        
        # 【新策略】通过文本内容查找弹窗，然后点击关闭按钮（不是直接隐藏）
        try:
            result = self.driver.execute_script("""
                // 需要关闭的弹窗关键词
                var keywords = ['学前必读', 'AI助教', '同学'];
                var closedCount = 0;
                var closedInfo = [];
                
                // 查找所有包含关键词的元素
                keywords.forEach(function(keyword) {
                    // 使用XPath查找包含关键词的元素
                    var xpath = "//*[contains(text(), '" + keyword + "')]";
                    var result = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                    
                    for (var i = 0; i < result.snapshotLength; i++) {
                        var element = result.snapshotItem(i);
                        
                        // 向上查找最近的弹窗容器（通常是div）
                        var container = element;
                        var maxDepth = 10;  // 最多向上查10层
                        while (container && maxDepth > 0) {
                            // 检查是否是弹窗容器（通常是position: fixed或absolute的div）
                            var style = window.getComputedStyle(container);
                            if (container.tagName === 'DIV' && 
                                (style.position === 'fixed' || style.position === 'absolute') &&
                                (style.zIndex > 100 || style.display === 'block')) {
                                
                                // 找到了弹窗容器，现在查找关闭按钮
                                if (style.display !== 'none') {
                                    // 多种关闭按钮选择器（按优先级排序）
                                    var closeSelectors = [
                                        'i.iconfont.iconguanbi',              // 学前必读的iconfont图标
                                        'img.ai-close-icon',                  // AI助手的图片关闭按钮
                                        'button[aria-label="Close"]',         // ARIA标签的关闭按钮
                                        'button.el-dialog__headerbtn',        // Element UI关闭按钮
                                        'i.el-dialog__close',                 // Element UI关闭图标
                                        'i.el-icon-close',                    // Element UI图标
                                        'img[alt="close"]',                   // alt="close"的图片
                                        'i.iconfont',                         // 通用iconfont图标
                                        '[class*="close"]',                   // 包含close的元素
                                        'button',                             // 最后尝试所有按钮
                                    ];
                                    
                                    var closeBtn = null;
                                    for (var j = 0; j < closeSelectors.length; j++) {
                                        closeBtn = container.querySelector(closeSelectors[j]);
                                        if (closeBtn) {
                                            // 检查按钮文本或属性是否与关闭相关
                                            var btnText = (closeBtn.textContent || '').trim();
                                            var btnClass = closeBtn.className || '';
                                            var btnAlt = closeBtn.getAttribute('alt') || '';
                                            if (btnText === '×' || btnText === '' || 
                                                btnClass.includes('close') || 
                                                btnAlt.includes('close') ||
                                                closeBtn.getAttribute('aria-label') === 'Close') {
                                                break;
                                            }
                                        }
                                    }
                                    
                                    if (closeBtn) {
                                        try {
                                            // 标记按钮需要点击（由Selenium在外部处理）
                                            closeBtn.setAttribute('data-needs-click', 'true');
                                            closedCount++;
                                            closedInfo.push({
                                                keyword: keyword,
                                                btnSelector: closeBtn.tagName + '.' + (closeBtn.className || 'no-class'),
                                                containerClass: container.className
                                            });
                                            console.log('标记关闭按钮待点击:', keyword, closeBtn.className || closeBtn.tagName);
                                        } catch(e) {
                                            console.error('标记关闭按钮失败:', e);
                                        }
                                        break;
                                    }
                                }
                            }
                            container = container.parentElement;
                            maxDepth--;
                        }
                    }
                });
                
                return {count: closedCount, info: closedInfo};
            """)
            
            if result and result.get('count', 0) > 0:
                # JS已标记按钮，现在用ActionChains点击（避免JS点击触发防脚本检测）
                try:
                    marked_buttons = self.driver.find_elements(By.XPATH, "//*[@data-needs-click='true']")
                    from selenium.webdriver.common.action_chains import ActionChains
                    for btn in marked_buttons:
                        try:
                            actions = ActionChains(self.driver)
                            actions.move_to_element(btn)
                            actions.click()
                            actions.perform()
                            self.smart_wait(0.5)
                        except:
                            pass
                except:
                    pass
                
                self.logger.info(f"✅ 已关闭 {result['count']} 个弹窗")
                for info in result.get('info', []):
                    self.logger.debug(f"  - 关键词: {info['keyword']}, 按钮: {info.get('btnSelector', 'unknown')}")
                self.smart_wait(1)  # 等待弹窗关闭动画完成
                return  # 成功关闭后直接返回
            else:
                self.logger.debug("未找到可关闭的弹窗")
        except Exception as e:
            self.logger.debug(f"点击关闭按钮失败: {e}")
        
        # 尝试15次，每次关闭一个弹窗后检查是否还有更多
        for attempt in range(15):
            # 先检查是否还有弹窗
            try:
                dialogs = self.driver.find_elements(By.XPATH, 
                    "//div[contains(@class, 'el-dialog__wrapper') and not(contains(@style, 'display: none'))]")
                if not dialogs:
                    self.logger.debug("✅ 未检测到弹窗")
                    break
                
                self.logger.debug(f"🔍 检测到 {len(dialogs)} 个弹窗，尝试关闭...")
            except:
                break
            
            closed_this_round = False
            
            # 按优先级尝试关闭按钮选择器（只尝试一次，成功后立即退出）
            close_button_selectors = [
                # 【最高优先级】ss2077自定义弹窗的关闭按钮（图片）
                "//div[contains(@class, 'ss2077-custom-dialog')]//img[@alt='close'][@class='icon']",  # 精确匹配
                "//div[contains(@class, 'ss2077-custom-title')]//img[@alt='close']",
                "//img[@alt='close'][@class='icon']",  # 通用图片关闭按钮
                
                # 学前必读弹窗的关闭按钮（优先点击<button>，不点击<i>）
                "//div[contains(text(), '学前必读')]/ancestor::div[contains(@class, 'el-dialog__wrapper')]//button[contains(@class, 'el-dialog__headerbtn')]",  # 通过文本定位
                "//div[contains(@class, 'el-dialog__wrapper')][not(contains(@class, 'ss2077'))]//button[contains(@class, 'el-dialog__headerbtn')]",  # 排除ss2077弹窗
                "//button[contains(@class, 'el-dialog__headerbtn')]",  # Element UI关闭按钮
                "//button[@aria-label='Close']",  # 有Close标签的按钮
                "//div[contains(@class, 'el-dialog__header')]//button",  # 弹窗头部的按钮
                
                # 通用关闭按钮
                "//button[contains(@class, 'close')]",
                "//*[normalize-space(text())='×']",
                "//*[contains(text(), '关闭')]",  # 文本匹配“关闭”
            ]
            
            for selector in close_button_selectors:
                try:
                    buttons = self.driver.find_elements(By.XPATH, selector)
                    if not buttons:
                        continue
                    
                    self.logger.debug(f"🔍 选择器找到 {len(buttons)} 个按钮: {selector[:60]}")
                    
                    # 只点击第一个按钮
                    btn = buttons[0]
                    
                    # 【建议1】确保按钮在视口中可见，滚动到视图中
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        self.smart_wait(0.3)  # 等待滚动完成
                    except:
                        pass
                    
                    # 【建议2】使用显式等待，确保元素可点击
                    try:
                        WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                    except:
                        pass
                    
                    # 【建议3】模拟用户行为：使用贝塞尔曲线移动鼠标到按钮上再点击
                    try:
                        # 【P2 - 反检测优化】使用曲线轨迹移动鼠标
                        if self.move_to_element_with_curve(btn):
                            self.logger.info(f"✅ 关闭弹窗(曲线移动): {selector[:60]}")
                            closed_this_round = True
                            self.smart_wait(1)  # 等待弹窗关闭动画完成
                            break
                    except:
                        # 如果鼠标移动点击失败，尝试普通点击
                        try:
                            btn.click()
                            self.logger.info(f"✅ 关闭弹窗: {selector[:60]}")
                            closed_this_round = True
                            self.smart_wait(1)
                            break
                        except:
                            # 普通点击失败，尝试ActionChains点击
                            try:
                                from selenium.webdriver.common.action_chains import ActionChains
                                actions = ActionChains(self.driver)
                                actions.move_to_element(btn)
                                actions.click()
                                actions.perform()
                                self.logger.info(f"✅ 关闭弹窗(ActionChains): {selector[:60]}")
                                closed_this_round = True
                                self.smart_wait(1)
                                break
                            except:
                                continue
                except Exception as e:
                    self.logger.debug(f"选择器处理失败: {str(e)[:50]}")
                    continue
            
            if not closed_this_round:
                # 没有找到可点击的按钮，退出
                self.logger.debug("⚠️  未找到可点击的关闭按钮")
                break
        
        # 检查是否还有可见的弹窗，如果有则保存HTML调试
        self.check_and_save_dialogs_for_debug()
        
    def select_options_by_letters(self, letters):
        """根据字母点击选项（支持多选）"""
        try:
            if isinstance(letters, str):
                letters = [letters]
            # 查找所有可见的选项容器
            option_xpaths = [
                "//div[contains(@class,'topic-item')]",
                "//li[contains(@class,'option')]",
                "//label[contains(@class,'el-radio') or contains(@class,'el-checkbox')]",
            ]
            options = []
            for xp in option_xpaths:
                try:
                    opts = self.driver.find_elements(By.XPATH, xp)
                    options.extend([o for o in opts if o.is_displayed()])
                except Exception:
                    continue
            if not options:
                self.logger.debug("未找到可点击选项容器")
                return False
            from selenium.webdriver.common.action_chains import ActionChains
            import re
            clicked = 0
            for letter in letters:
                target = None
                # 在选项容器中匹配以字母开头的文本
                for opt in options:
                    try:
                        txt = (opt.text or '').strip()
                        if re.match(rf"^\s*{letter}[\.|、|）|)]", txt):
                            target = opt
                            break
                        # 备用：查找包含字母标签的span
                        spans = opt.find_elements(By.XPATH, ".//span")
                        for sp in spans:
                            if (sp.text or '').strip().startswith(letter):
                                target = opt
                                break
                        if target:
                            break
                    except Exception:
                        continue
                if target:
                    try:
                        # 滚动到视图并点击
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                        self.smart_wait(0.3)
                        actions = ActionChains(self.driver)
                        actions.move_to_element(target)
                        actions.click()
                        actions.perform()
                        clicked += 1
                        self.smart_wait(0.3)
                        self.logger.info(f"✅ 已点击选项: {letter}")
                    except Exception:
                        pass
                else:
                    self.logger.debug(f"未找到选项: {letter}")
            return clicked > 0
        except Exception as e:
            self.logger.debug(f"选择选项失败: {e}")
            return False    
    def check_and_save_dialogs_for_debug(self):
        """检查是否还有未关闭的弹窗，并保存HTML供调试"""
        try:
            # 查找可能的弹窗元素
            dialog_selectors = [
                "//div[contains(@class, 'dialog') and contains(@style, 'display')]",
                "//div[contains(@class, 'modal') and contains(@style, 'display')]",
                "//div[contains(@class, 'popup')]",
                "//div[contains(@class, 'el-dialog__wrapper')]",
            ]
            
            found_dialogs = []
            for selector in dialog_selectors:
                try:
                    dialogs = self.driver.find_elements(By.XPATH, selector)
                    for dialog in dialogs:
                        if dialog.is_displayed():
                            found_dialogs.append(dialog)
                except:
                    continue
            
            if found_dialogs:
                self.logger.warning(f"⚠️  检测到 {len(found_dialogs)} 个未关闭的弹窗，保存HTML供调试...")
                
                # 保存完整页面HTML
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                html_file = f'debug_dialogs_{timestamp}.html'
                
                try:
                    with open(html_file, 'w', encoding='utf-8') as f:
                        f.write(self.driver.page_source)
                    self.logger.info(f"💾 已保存完整HTML: {html_file}")
                except Exception as e:
                    self.logger.error(f"保存HTML失败: {e}")
                
                # 保存每个弹窗的HTML片段
                for idx, dialog in enumerate(found_dialogs, 1):
                    try:
                        dialog_html = dialog.get_attribute('outerHTML')
                        dialog_file = f'debug_dialog_{idx}_{timestamp}.html'
                        with open(dialog_file, 'w', encoding='utf-8') as f:
                            f.write(dialog_html)
                        self.logger.info(f"💾 已保存弹窗{idx}: {dialog_file}")
                        
                        # 输出弹窗的class和id信息
                        dialog_class = dialog.get_attribute('class') or ''
                        dialog_id = dialog.get_attribute('id') or ''
                        self.logger.info(f"  弹窗{idx} class: {dialog_class[:100]}")
                        if dialog_id:
                            self.logger.info(f"  弹窗{idx} id: {dialog_id}")
                    except Exception as e:
                        self.logger.error(f"保存弹窗{idx}HTML失败: {e}")
                
                # 保存截图
                try:
                    screenshot_file = f'debug_dialogs_{timestamp}.png'
                    self.driver.save_screenshot(screenshot_file)
                    self.logger.info(f"📸 已保存截图: {screenshot_file}")
                except Exception as e:
                    self.logger.error(f"保存截图失败: {e}")
                
                self.logger.warning("🔍 请查看以上调试文件分析弹窗结构")
            
        except Exception as e:
            self.logger.debug(f"检查弹窗调试信息失败: {e}")
    
    def get_video_progress(self):
        """获取视频当前播放进度（秒）"""
        try:
            progress = self.driver.execute_script("""
                var video = document.querySelector('video');
                if (video) {
                    return video.currentTime;
                }
                return 0;
            """)
            return float(progress) if progress else 0
        except Exception as e:
            self.logger.debug(f"获取视频进度失败: {e}")
            return 0
    
    def ensure_video_playing(self):
        """确保视频正在播放"""
        try:
            is_playing = self.driver.execute_script("""
                var video = document.querySelector('video');
                if (video) {
                    return !video.paused && !video.ended;
                }
                return false;
            """)
            return bool(is_playing)
        except Exception as e:
            self.logger.debug(f"检查视频播放状态失败: {e}")
            return False
    
    def recover_stuck_video(self):
        """恢复卡停的视频（使用ActionChains模拟真实点击）"""
        try:
            self.logger.warning("🔧 检测到视频卡停，开始恢复...")
            
            # 策略1：使用ActionChains点击视频中央区域（模拟真实用户操作）
            try:
                self.logger.info("📍 尝试点击视频中央区域恢复播放...")
                video = self.driver.find_element(By.XPATH, "//video")
                
                # 使用ActionChains模拟真实点击，添加随机偏移
                import random
                from selenium.webdriver.common.action_chains import ActionChains
                
                # 获取视频元素的大小
                size = video.size
                width = size['width']
                height = size['height']
                
                # 计算中央位置，添加小范围随机偏移（避免每次点击完全相同的位置）
                offset_x = width // 2 + random.randint(-20, 20)
                offset_y = height // 2 + random.randint(-20, 20)
                
                # 使用ActionChains移动到视频中央并点击
                actions = ActionChains(self.driver)
                actions.move_to_element_with_offset(video, offset_x - width // 2, offset_y - height // 2)
                actions.click()
                actions.perform()
                
                self.logger.info(f"✅ 已点击视频中央 (偏移: {offset_x}, {offset_y})")
            except Exception as e:
                self.logger.warning(f"点击视频中央失败: {e}")
            
            self.smart_wait(2)
            return True
            
        except Exception as e:
            self.logger.error(f"恢复卡停视频失败: {e}")
            return False
    
    def check_for_quiz(self):
        """检查是否有题目弹窗"""
        try:
            # 先检查是否是ss2077自定义弹窗（AI助手），如果是则不是题目
            try:
                ss2077_dialogs = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'ss2077-custom-dialog')]")
                if ss2077_dialogs and any(d.is_displayed() for d in ss2077_dialogs):
                    self.logger.debug("检测到ss2077自定义弹窗，不是题目弹窗")
                    return False
            except:
                pass
            
            # 查找题目弹窗的常见选择器
            quiz_selectors = [
                "//div[contains(@class, 'topic-item')]",  # 题目容器
                "//div[contains(@class, 'subject-item')]",  # 题目项
                "//div[contains(@class, 'popTopicChoose')]",  # 弹窗题目
                "//*[contains(text(), 'AI助教') or contains(text(), '出题')]",  # AI助教弹窗
                "//*[contains(text(), '题目') or contains(text(), '选择')]",
                "//div[contains(@class, 'el-dialog') and contains(@style, 'display')]//input[@type='radio']",  # Element UI对话框
            ]
            
            for selector in quiz_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements and any(elem.is_displayed() for elem in elements):
                        self.logger.info(f"🎯 检测到题目弹窗: {selector}")
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            self.logger.debug(f"检查题目弹窗失败: {e}")
            return False
    
    def answer_quiz(self):
        """回答题目（支持多次作答，识别正确/错误答案）"""
        try:
            self.logger.info("📝 开始回答题目...")
            
            # 【P0 - 反检测优化】添加"阅读题目"时间，模拟用户看题干
            import random
            reading_time = random.uniform(5, 10)
            self.logger.info(f"📖 模拟阅读题目时间: {reading_time:.2f} 秒")
            self.smart_wait(reading_time)
            
            # 查找所有选项元素（优先级从高到低）
            # 【P1 - 反检测优化】减少选择器数量，只保留最常用的选择器
            # 【修复】添加知到平台专用选择器 li.topic-item（最高优先级）
            # 【修复2】添加显式等待，确保选项元素已加载
            option_selectors = [
                "//li[contains(@class, 'topic-item')]",  # 知到平台题目选项（最高优先级）
                "//input[@type='radio']",  # 单选框
                "//input[@type='checkbox']",  # 多选框
                "//label[contains(@class, 'el-radio')]",  # Element UI单选框标签
                "//label[contains(@class, 'el-checkbox')]",  # Element UI多选框标签
            ]
            
            options = []
            for selector in option_selectors:
                try:
                    # 【新增】添加显式等待，等待选项元素出现
                    from selenium.webdriver.support.ui import WebDriverWait
                    from selenium.webdriver.support import expected_conditions as EC
                    
                    # 等待至少一个选项元素可见（最多等待5秒）
                    try:
                        WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                    except:
                        # 如果等待超时，继续尝试下一个选择器
                        continue
                    
                    # 再等待一小段时间确保元素完全渲染
                    self.smart_wait(0.5)
                    
                    found_options = self.driver.find_elements(By.XPATH, selector)
                    if found_options:
                        # 过滤出可见的选项
                        visible_options = [opt for opt in found_options if opt.is_displayed()]
                        if visible_options:
                            options = visible_options
                            self.logger.info(f"🔍 找到 {len(visible_options)} 个选项: {selector}")
                            break  # 找到就停止，使用优先级最高的
                except Exception as e:
                    self.logger.debug(f"选择器 {selector} 查找失败: {e}")
                    continue
            
            if not options:
                self.logger.warning("⚠️  未找到题目选项")
                
                # 【新增】保存调试信息
                try:
                    import os
                    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug_quiz')
                    os.makedirs(debug_dir, exist_ok=True)
                    
                    # 保存完整HTML
                    html_path = os.path.join(debug_dir, f'quiz_no_options_{int(time.time())}.html')
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(self.driver.page_source)
                    self.logger.info(f"💾 已保存题目HTML到: {html_path}")
                    
                    # 保存截图
                    screenshot_path = os.path.join(debug_dir, f'quiz_no_options_{int(time.time())}.png')
                    self.driver.save_screenshot(screenshot_path)
                    self.logger.info(f"📸 已保存题目截图到: {screenshot_path}")
                except Exception as e:
                    self.logger.debug(f"保存调试信息失败: {e}")
                
                return False
            
            # 检测题目类型（单选/多选）
            is_multiple_choice = False
            try:
                # 检查是否有多选框
                checkbox_inputs = self.driver.find_elements(By.XPATH, "//input[@type='checkbox']")
                checkbox_labels = self.driver.find_elements(By.XPATH, "//label[contains(@class, 'el-checkbox')]")
                if checkbox_inputs or checkbox_labels:
                    is_multiple_choice = True
                    self.logger.info("📝 检测到多选题")
                else:
                    self.logger.info("📝 检测到单选题")
            except:
                pass
            
            # 依次尝试每个选项，直到正确
            option_labels = ['A', 'B', 'C', 'D']
            max_attempts = min(len(options), 4)  # 最多尝试4个选项
            
            # 【P0 - 反检测优化】打乱选项尝试顺序，不再固定A→B→C→D
            attempt_indices = list(range(max_attempts))
            random.shuffle(attempt_indices)  # 随机打乱顺序
            self.logger.info(f"🎲 选项尝试顺序: {[option_labels[i] for i in attempt_indices]}")
            
            for attempt_idx in attempt_indices:
                current_label = option_labels[attempt_idx] if attempt_idx < len(option_labels) else f"选项{attempt_idx+1}"
                try:
                    current_option = options[attempt_idx]
                    
                    self.logger.info(f"🎯 尝试选择 {current_label}...")
                    
                    # 【反检测】随机延时0-3秒后再点击选项
                    import random
                    random_delay = random.uniform(0, 3)
                    self.logger.info(f"⏰ 随机延时 {random_delay:.2f} 秒（避免检测）")
                    self.smart_wait(random_delay)
                    
                    # 点击选项
                    try:
                        current_option.click()
                        self.smart_wait(0.5)
                    except:
                        # 如果直接点击失败，尝试用ActionChains点击
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(self.driver)
                        actions.move_to_element(current_option)
                        actions.click()
                        actions.perform()
                        self.smart_wait(0.5)
                    
                    # 查找并点击确定/提交按钮
                    # 【P1 - 反检测优化】减少选择器数量，只保疙3个最常用
                    submit_buttons = [
                        "//span[contains(text(), '确定')]",
                        "//button[contains(text(), '确定')]",
                        "//div[contains(@class, 'popbtn_ok')]",  # 知到平台的确定按钮
                    ]
                    
                    # 【P1 - 反检测优化】扩大提交延时范围到2-6秒
                    submit_delay = random.uniform(2, 6)
                    self.logger.info(f"⏰ 提交前随机等待 {submit_delay:.2f} 秒")
                    self.smart_wait(submit_delay)
                    
                    # 【反检测优化】模拟犹豫，50%概率额外延时0.5-1秒
                    if random.random() < 0.5:
                        hesitation = random.uniform(0.5, 1)
                        self.logger.info(f"🤔 模拟犹豫 {hesitation:.2f} 秒")
                        self.smart_wait(hesitation)
                    
                    submit_clicked = False
                    for btn_selector in submit_buttons:
                        try:
                            submit_btns = self.driver.find_elements(By.XPATH, btn_selector)
                            for submit_btn in submit_btns:
                                if submit_btn.is_displayed() and submit_btn.is_enabled():
                                    try:
                                        submit_btn.click()
                                        self.logger.info("✅ 已点击提交")
                                        submit_clicked = True
                                        break
                                    except:
                                        try:
                                            from selenium.webdriver.common.action_chains import ActionChains
                                            actions = ActionChains(self.driver)
                                            actions.move_to_element(submit_btn)
                                            actions.click()
                                            actions.perform()
                                            self.logger.info("✅ ActionChains点击提交")
                                            submit_clicked = True
                                            break
                                        except:
                                            continue
                            if submit_clicked:
                                break
                        except:
                            continue
                    
                    if submit_clicked:
                        self.smart_wait(1.5)  # 等待反馈
                    
                    # 检查答案是否正确
                    answer_result = self.check_answer_result()
                    
                    if answer_result == 'correct':
                        self.logger.info(f"✅ {current_label} 是正确答案！")
                        self.quizzes_answered_this_session += 1
                        self.progress['total_quizzes'] += 1
                        
                        # 【P0 - 反检测优化】答对后查看结果时间，2-4秒
                        result_view_time = random.uniform(2, 4)
                        self.logger.info(f"📊 查看答题结果 {result_view_time:.2f} 秒")
                        self.smart_wait(result_view_time)
                        
                        # 点击关闭按钮关闭题目弹窗
                        if self.close_quiz_dialog():
                            self.logger.info("✅ 已点击关闭按钮关闭题目弹窗")
                        else:
                            self.logger.warning("⚠️  关闭题目弹窗失败")
                        
                        # 【新增】点击视频中央恢复播放（模拟真实点击+随机偏移）
                        try:
                            video_element = self.driver.find_element(By.TAG_NAME, 'video')
                            if video_element:
                                # 获取视频元素的位置和大小
                                location = video_element.location
                                size = video_element.size
                                
                                # 计算中心点
                                center_x = location['x'] + size['width'] // 2
                                center_y = location['y'] + size['height'] // 2
                                
                                # 添加随机偏移（±50像素）
                                import random
                                offset_x = random.randint(-50, 50)
                                offset_y = random.randint(-50, 50)
                                
                                self.logger.info(f"📍 视频中心: ({center_x}, {center_y}), 偏移: ({offset_x:+d}, {offset_y:+d})")
                                
                                # 使用ActionChains点击指定坐标
                                from selenium.webdriver.common.action_chains import ActionChains
                                actions = ActionChains(self.driver)
                                actions.move_to_element_with_offset(video_element, offset_x, offset_y)
                                actions.click()
                                actions.perform()
                                
                                self.logger.info("🎬 已点击视频恢复播放（含随机偏移）")
                                self.smart_wait(1)
                            else:
                                self.logger.warning("⚠️  未找到video元素")
                        except Exception as e:
                            self.logger.warning(f"⚠️  点击视频中央失败: {e}")
                        
                        return True
                        
                    elif answer_result == 'wrong':
                        self.logger.warning(f"❌ {current_label} 不正确")
                        
                        # 尝试提取正确答案
                        correct_answer = self.extract_correct_answer()
                        if correct_answer:
                            self.logger.info(f"💡 正确答案是: {correct_answer}")
                            
                            # 尝试点击正确答案
                            if self.click_correct_answer(correct_answer, options):
                                self.logger.info("✅ 已选择正确答案")
                                
                                # 再次提交
                                for btn_selector in submit_buttons:
                                    try:
                                        submit_btns = self.driver.find_elements(By.XPATH, btn_selector)
                                        for submit_btn in submit_btns:
                                            if submit_btn.is_displayed() and submit_btn.is_enabled():
                                                submit_btn.click()
                                                self.logger.info("✅ 已重新提交")
                                                self.smart_wait(1.5)
                                                break
                                        break
                                    except:
                                        continue
                                
                                self.quizzes_answered_this_session += 1
                                self.progress['total_quizzes'] += 1
                                
                                # 【P0 - 反检测优化】答错后查看正确答案解析，2-4秒
                                answer_review_time = random.uniform(2, 4)
                                self.logger.info(f"💡 查看正确答案解析 {answer_review_time:.2f} 秒")
                                self.smart_wait(answer_review_time)
                                
                                # 点击关闭按钮关闭题目弹窗
                                if self.close_quiz_dialog():
                                    self.logger.info("✅ 已点击关闭按钮关闭题目弹窗")
                                else:
                                    self.logger.warning("⚠️  关闭题目弹窗失败")
                                
                                # 【新增】点击视频中央恢复播放（模拟真实点击+随机偏移）
                                try:
                                    video_element = self.driver.find_element(By.TAG_NAME, 'video')
                                    if video_element:
                                        # 获取视频元素的位置和大小
                                        location = video_element.location
                                        size = video_element.size
                                        
                                        # 计算中心点
                                        center_x = location['x'] + size['width'] // 2
                                        center_y = location['y'] + size['height'] // 2
                                        
                                        # 添加随机偏移（±50像素）
                                        import random
                                        offset_x = random.randint(-50, 50)
                                        offset_y = random.randint(-50, 50)
                                        
                                        self.logger.info(f"📍 视频中心: ({center_x}, {center_y}), 偏移: ({offset_x:+d}, {offset_y:+d})")
                                        
                                        # 使用ActionChains点击指定坐标
                                        from selenium.webdriver.common.action_chains import ActionChains
                                        actions = ActionChains(self.driver)
                                        actions.move_to_element_with_offset(video_element, offset_x, offset_y)
                                        actions.click()
                                        actions.perform()
                                        
                                        self.logger.info("🎬 已点击视频恢复播放（含随机偏移）")
                                        self.smart_wait(1)
                                    else:
                                        self.logger.warning("⚠️  未找到video元素")
                                except Exception as e:
                                    self.logger.warning(f"⚠️  点击视频中央失败: {e}")
                                
                                return True
                        
                        # 继续下一个选项
                        continue
                    else:
                        self.logger.debug("⚠️  未检测到明确的结果，继续尝试...")
                        continue
                    
                except Exception as e:
                    self.logger.error(f"尝试选项 {current_label} 失败: {e}")
                    continue
            
            # 所有选项都尝试完了，可能是多选题
            self.logger.warning("⚠️  所有选项都尝试完毕，未找到单个正确答案")
            
            # 如果是多选题或者所有单选都尝试过了，选择所有选项ABCD后直接关闭
            if is_multiple_choice or max_attempts >= 4:
                self.logger.info("💡 疑似多选题或无法确定答案，选择所有选项ABCD后关闭...")
                
                # 【P1 - 反检测优化】多选题选项也要随机打乱顺序
                option_count = min(4, len(options))
                select_indices = list(range(option_count))
                random.shuffle(select_indices)  # 随机打乱选择顺序
                self.logger.info(f"🎲 多选题选项顺序: {[option_labels[i] for i in select_indices]}")
                
                # 选择所有选项
                all_selected = True
                for idx in select_indices:
                    try:
                        option = options[idx]
                        label = option_labels[idx] if idx < len(option_labels) else f"选项{idx+1}"
                        
                        # 检查是否已选中
                        is_selected = False
                        try:
                            # 对于checkbox和radio，检查checked属性
                            tag_name = option.tag_name.lower()
                            if tag_name == 'input':
                                is_selected = option.is_selected()
                            else:
                                # 对于label等元素，查找内部的input
                                inner_input = option.find_element(By.XPATH, ".//input")
                                is_selected = inner_input.is_selected()
                        except:
                            pass
                        
                        if not is_selected:
                            self.logger.info(f"🎯 选择 {label}")
                            
                            # 【反检测】随机延时0-3秒后再点击选项
                            import random
                            random_delay = random.uniform(0, 3)
                            self.logger.info(f"⏰ 随机延时 {random_delay:.2f} 秒（避免检测）")
                            self.smart_wait(random_delay)
                            
                            try:
                                option.click()
                                self.smart_wait(0.3)
                            except:
                                try:
                                    from selenium.webdriver.common.action_chains import ActionChains
                                    actions = ActionChains(self.driver)
                                    actions.move_to_element(option)
                                    actions.click()
                                    actions.perform()
                                    self.smart_wait(0.3)
                                except Exception as e:
                                    self.logger.warning(f"⚠️  选择 {label} 失败: {e}")
                                    all_selected = False
                        else:
                            self.logger.debug(f"✓ {label} 已选中")
                            
                    except Exception as e:
                        self.logger.error(f"选择选项失败: {e}")
                        all_selected = False
                
                # 尝试提交（可选）
                submit_buttons = [
                    "//span[contains(text(), '确定')]",
                    "//button[contains(text(), '确定')]",
                    "//span[contains(text(), '提交')]",
                    "//button[contains(text(), '提交')]",
                    "//div[contains(@class, 'popbtn_ok')]",
                ]
                
                submit_clicked = False
                for btn_selector in submit_buttons:
                    try:
                        submit_btns = self.driver.find_elements(By.XPATH, btn_selector)
                        for submit_btn in submit_btns:
                            if submit_btn.is_displayed() and submit_btn.is_enabled():
                                try:
                                    submit_btn.click()
                                    self.logger.info("✅ 已点击提交")
                                    submit_clicked = True
                                    self.smart_wait(1)
                                    break
                                except:
                                    try:
                                        from selenium.webdriver.common.action_chains import ActionChains
                                        actions = ActionChains(self.driver)
                                        actions.move_to_element(submit_btn)
                                        actions.click()
                                        actions.perform()
                                        self.logger.info("✅ ActionChains点击提交")
                                        submit_clicked = True
                                        self.smart_wait(1)
                                        break
                                    except:
                                        continue
                        if submit_clicked:
                            break
                    except:
                        continue
                
                # 点击关闭按钮关闭题目弹窗
                self.logger.info("🔄 点击关闭按钮关闭题目弹窗...")
                if self.close_quiz_dialog():
                    self.logger.info("✅ 多选题已处理并关闭")
                    self.quizzes_answered_this_session += 1
                    self.progress['total_quizzes'] += 1
                    self.smart_wait(1)
                else:
                    self.logger.warning("⚠️  关闭题目弹窗失败")
                    return False
                
                # 【新增】点击视频中央恢复播放（模拟真实点击+随机偏移）
                try:
                    video_element = self.driver.find_element(By.TAG_NAME, 'video')
                    if video_element:
                        # 获取视频元素的位置和大小
                        location = video_element.location
                        size = video_element.size
                        
                        # 计算中心点
                        center_x = location['x'] + size['width'] // 2
                        center_y = location['y'] + size['height'] // 2
                        
                        # 添加随机偏移（±50像素）
                        import random
                        offset_x = random.randint(-50, 50)
                        offset_y = random.randint(-50, 50)
                        
                        self.logger.info(f"📍 视频中心: ({center_x}, {center_y}), 偏移: ({offset_x:+d}, {offset_y:+d})")
                        
                        # 使用ActionChains点击指定坐标
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(self.driver)
                        actions.move_to_element_with_offset(video_element, offset_x, offset_y)
                        actions.click()
                        actions.perform()
                        
                        self.logger.info("🎬 已点击视频恢复播放（含随机偏移）")
                        self.smart_wait(1)
                        return True
                    else:
                        self.logger.warning("⚠️  未找到video元素")
                        return True  # 即使点击失败也返回True，因为题目已处理
                except Exception as e:
                    self.logger.warning(f"⚠️  点击视频中央失败: {e}")
                    return True  # 即使点击失败也返回True，因为题目已处理
            
            return False
            
        except Exception as e:
            self.logger.error(f"回答题目失败: {e}")
            return False
    
    def check_answer_correct(self):
        """检查答案是否正确"""
        try:
            # 检查是否有"正确"提示
            correct_selectors = [
                "//*[contains(text(), '正确')]",
                "//*[contains(text(), '√')]",
                "//*[contains(@class, 'correct')]",
                "//*[contains(@class, 'success')]",
                "//i[contains(@class, 'el-icon-success')]",
                "//i[contains(@class, 'el-icon-check')]",
            ]
            
            for selector in correct_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements:
                        for elem in elements:
                            if elem.is_displayed():
                                text = elem.text.strip()
                                # 排除包含"错误"的元素
                                if '正确' in text or '√' in text:
                                    if '错误' not in text:
                                        self.logger.debug(f"检测到正确标记: {text}")
                                        return True
                except:
                    continue
            
            # 检查是否有"错误"提示（明确的错误标记）
            error_selectors = [
                "//*[contains(text(), '错误')]",
                "//*[contains(text(), '×')]",
                "//*[contains(@class, 'error')]",
                "//*[contains(@class, 'wrong')]",
                "//i[contains(@class, 'el-icon-error')]",
                "//i[contains(@class, 'el-icon-close')]",
            ]
            
            for selector in error_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements:
                        for elem in elements:
                            if elem.is_displayed():
                                text = elem.text.strip()
                                if '错误' in text or '×' in text:
                                    self.logger.debug(f"检测到错误标记: {text}")
                                    return False
                except:
                    continue
            
            # 如果既没有正确也没有错误提示，返回False（继续尝试）
            return False
            
        except Exception as e:
            self.logger.debug(f"检查答案正确性失败: {e}")
            return False
    
    def check_answer_result(self):
        """检查答案结果（返回 'correct', 'wrong' 或 None）"""
        try:
            # 【优先检查】先检查是否有"错误"提示（避免误判）
            error_selectors = [
                "//span[@class='error']",  # 【精确匹配】知到平台红色错误标记（仅匹配class="error"）
                "//span[contains(@class, 'error') and contains(@class, 'answer')]",  # 匹配 class="error answer-text" 等组合
                "//*[contains(text(), '回答错误')]",
                "//*[contains(text(), '答题错误')]",
                "//*[contains(@class, 'colorRed')]",  # 知到平台红色错误标记
                "//*[contains(@class, 'wrong')]",
            ]
            
            for selector in error_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            elem_class = elem.get_attribute('class') or ''
                            elem_text = elem.text.strip()
                            
                            # 调试：记录元素详情
                            self.logger.debug(f"检查错误标记元素: tag={elem.tag_name}, class='{elem_class}', text='{elem_text}'")
                            
                            # 【精确判断】必须是纯 'error' class 或包含明确错误文本
                            if elem_class == 'error' or 'error answer' in elem_class:
                                self.logger.info(f"✗ 检测到错误标记: <{elem.tag_name} class='{elem_class}'>")
                                return 'wrong'
                            
                            # 检查文本内容
                            if elem_text and ('回答错误' in elem_text or '答题错误' in elem_text):
                                self.logger.info(f"✗ 检测到错误文本: {elem_text}")
                                return 'wrong'
                            
                            # 检查包含"错误"但排除"正确"的情况
                            if elem_text and '错误' in elem_text and '正确' not in elem_text:
                                self.logger.info(f"✗ 检测到错误标记: {elem_text}")
                                return 'wrong'
                except Exception as e:
                    self.logger.debug(f"检查错误选择器 {selector} 失败: {e}")
                    continue
            
            # 【再检查】是否有"正确"提示
            correct_selectors = [
                "//span[@class='right']",  # 【精确匹配】知到平台绿色勾标记（仅匹配class="right"）
                "//span[contains(@class, 'right') and contains(@class, 'answer')]",  # 匹配 class="right answer-text" 等组合
                "//*[contains(text(), '回答正确')]",
                "//*[contains(text(), '答题正确')]",
                "//*[contains(@class, 'colorGreen')]",  # 知到平台绿色正确标记
                "//*[contains(@class, 'correct')]",
                "//*[contains(@class, 'success')]",
            ]
            
            for selector in correct_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            elem_class = elem.get_attribute('class') or ''
                            elem_text = elem.text.strip()
                            
                            # 调试：记录元素详情
                            self.logger.debug(f"检查正确标记元素: tag={elem.tag_name}, class='{elem_class}', text='{elem_text}'")
                            
                            # 【精确判断】必须是纯 'right' class 或包含明确正确文本
                            if elem_class == 'right' or 'right answer' in elem_class:
                                self.logger.info(f"✓ 检测到正确标记: <{elem.tag_name} class='{elem_class}'>")
                                return 'correct'
                            
                            # 检查文本内容
                            if elem_text and ('回答正确' in elem_text or '答题正确' in elem_text):
                                self.logger.info(f"✓ 检测到正确文本: {elem_text}")
                                return 'correct'
                            
                            # 检查包含"正确"但排除"错误"的情况
                            if elem_text and '正确' in elem_text and '错误' not in elem_text:
                                self.logger.info(f"✓ 检测到正确标记: {elem_text}")
                                return 'correct'
                except Exception as e:
                    self.logger.debug(f"检查正确选择器 {selector} 失败: {e}")
                    continue
            
            # 【调试】如果既没有正确也没有错误，保存HTML用于分析
            self.logger.debug("⚠️  未检测到明确的正确或错误标记")
            return None
            
        except Exception as e:
            self.logger.debug(f"检查答案结果失败: {e}")
            return None
    
    def extract_correct_answers(self):
        """提取正确答案（支持多选，滚动弹窗以完整展示答案）"""
        try:
            # 优先滚动弹窗容器，避免只看到一部分答案
            try:
                dialog_wrappers = self.driver.find_elements(By.XPATH,
                    "//div[contains(@class,'el-dialog__wrapper') and not(contains(@style,'display: none'))]")
                for wrap in dialog_wrappers:
                    try:
                        self.driver.execute_script(
                            "arguments[0].scrollTop = arguments[0].scrollHeight;", wrap)
                        self.smart_wait(0.3)
                    except Exception:
                        pass
            except Exception:
                pass
            
            # 查找包含正确答案的元素
            answer_selectors = [
                "//p[contains(@class, 'answer')]",  # 知到平台 <p class="answer">
                "//*[contains(text(), '正确答案')]",
                "//*[contains(text(), '正确选项')]",
                "//*[contains(@class, 'correct-answer')]",
                "//*[contains(@class, 'right-answer')]",
            ]
            
            import re
            letters = []
            # 支持多选题扩展选项：A-Z（常见为A-L）
            letter_pattern = r"[A-Z]"
            for selector in answer_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            text = elem.text.strip()
                            # 提取所有答案字母（A-Z），避免只识别一个
                            found = re.findall(letter_pattern, text)
                            if found:
                                letters.extend(found)
                except Exception:
                    continue
            
            # 去重并按字母顺序
            letters = sorted(list(dict.fromkeys(letters)))
            if letters:
                self.logger.info(f"✅ 提取到正确答案: {', '.join(letters)}")
                return letters
            return None
            
        except Exception as e:
            self.logger.debug(f"提取正确答案失败: {e}")
            return None
    
    def click_correct_answer(self, answer_letter, options):
        """点击正确答案（兼容扩展选项 A-Z）"""
        try:
            # 将字母转换为索引（A->0, B->1, ... Z->25）
            answer_letter = str(answer_letter).strip().upper()
            if not answer_letter or not ('A' <= answer_letter <= 'Z'):
                return False
            answer_index = ord(answer_letter) - ord('A')
            
            if 0 <= answer_index < len(options):
                correct_option = options[answer_index]
                
                try:
                    correct_option.click()
                    self.smart_wait(0.5)
                    return True
                except:
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(self.driver)
                        actions.move_to_element(correct_option)
                        actions.click()
                        actions.perform()
                        self.smart_wait(0.5)
                        return True
                    except:
                        return False
            
            return False
            
        except Exception as e:
            self.logger.debug(f"点击正确答案失败: {e}")
            return False
    
    def close_quiz_dialog(self):
        """关闭题目对话框"""
        try:
            # 【P0 - 反检测优化】关闭题目弹窗前延长等待时间到2-5秒
            import random
            close_delay = random.uniform(2, 5)
            self.logger.info(f"⏳ 关闭弹窗前等待 {close_delay:.2f} 秒")
            self.smart_wait(close_delay)
            
            # 【P1 - 反检测优化】减少选择器数量，并优先点击底部“关闭”按钮
            # 先滚动到底，确保footer可见
            try:
                self.scroll_quiz_dialog('bottom')
            except Exception:
                pass
            # 优先尝试 footer 按钮（span.dialog-footer > div.btn 文本含“关闭”）
            try:
                footer_btns = self.driver.find_elements(By.XPATH,
                    "//span[contains(@class, 'dialog-footer')]//div[contains(@class, 'btn') and (text()='关闭' or contains(text(),'关闭'))]")
                for fb in footer_btns:
                    if fb.is_displayed():
                        try:
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", fb)
                        except Exception:
                            pass
                        try:
                            fb.click()
                            self.logger.info("✅ 已点击底部关闭按钮")
                            self.smart_wait(1)
                            return True
                        except Exception:
                            # 备用：ActionChains 点击
                            try:
                                from selenium.webdriver.common.action_chains import ActionChains
                                actions = ActionChains(self.driver)
                                actions.move_to_element(fb)
                                actions.click()
                                actions.perform()
                                self.logger.info("✅ 已点击底部关闭按钮(ActionChains)")
                                self.smart_wait(1)
                                return True
                            except Exception:
                                continue
            except Exception:
                pass
            close_selectors = [
                # Element UI标准关闭按钮（头部X）
                "//button[contains(@class, 'el-dialog__headerbtn')]",
                # 文本为"关闭"的按钮（通用）
                "//button[contains(text(), '关闭')]",
                # 兜底：任意footer下的div.btn
                "//span[contains(@class, 'dialog-footer')]//div[contains(@class, 'btn')]",
            ]
            
            for selector in close_selectors:
                try:
                    close_btns = self.driver.find_elements(By.XPATH, selector)
                    for close_btn in close_btns:
                        if close_btn.is_displayed():
                            # 尝试普通点击
                            try:
                                close_btn.click()
                                self.logger.info(f"✅ 已关闭题目弹窗: {selector[:60]}")
                                self.smart_wait(1)
                                return True
                            except:
                                # 如果普通点击失败，尝试ActionChains点击
                                try:
                                    from selenium.webdriver.common.action_chains import ActionChains
                                    actions = ActionChains(self.driver)
                                    actions.move_to_element(close_btn)
                                    actions.click()
                                    actions.perform()
                                    self.logger.info(f"✅ 已关闭题目弹窗(ActionChains): {selector[:60]}")
                                    self.smart_wait(1)
                                    return True
                                except:
                                    continue
                except:
                    continue
            
            self.logger.warning("⚠️  未找到题目弹窗的关闭按钮")
            return False
            
        except Exception as e:
            self.logger.debug(f"关闭题目弹窗失败: {e}")
            return False
    
    def get_quiz_options(self):
        """获取当前题目选项元素列表（可见）"""
        try:
            option_xpaths = [
                "//li[contains(@class,'topic-item')]",
                "//li[contains(@class,'option')]",
                "//label[contains(@class,'el-radio') or contains(@class,'el-checkbox')]",
            ]
            options = []
            for xp in option_xpaths:
                try:
                    opts = self.driver.find_elements(By.XPATH, xp)
                    options.extend([o for o in opts if o.is_displayed()])
                except Exception:
                    continue
            return options
        except Exception:
            return []

    def is_multi_choice(self):
        """判断是否为多选题"""
        try:
            elems = self.driver.find_elements(By.XPATH, "//span[contains(@class,'title-tit')]")
            for e in elems:
                if e.is_displayed():
                    t = (e.text or '').strip()
                    if '多选题' in t:
                        return True
            # 备用：有checkbox即视为多选
            checkboxes = self.driver.find_elements(By.XPATH, "//label[contains(@class,'el-checkbox')]")
            return len([c for c in checkboxes if c.is_displayed()]) > 0
        except Exception:
            return False

    def scroll_quiz_dialog(self, position='bottom'):
        """滚动题目弹窗视图，确保答案或选项完全可见"""
        try:
            wrappers = self.driver.find_elements(By.XPATH, "//div[contains(@class,'el-dialog__wrapper') and not(contains(@style,'display: none'))]")
            for w in wrappers:
                try:
                    view = None
                    try:
                        view = w.find_element(By.XPATH, ".//div[contains(@class,'el-scrollbar__wrap')]")
                    except Exception:
                        view = w
                    if position == 'top':
                        self.driver.execute_script("arguments[0].scrollTop = 0;", view)
                    elif position == 'center':
                        self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight/2;", view)
                    else:
                        self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", view)
                    self.smart_wait(0.4)
                except Exception:
                    continue
        except Exception:
            pass

    def start_quiz_monitor(self):
        """启动题目实时监控线程（独立线程，异步检测）"""
        def monitor_loop():
            self.logger.info("👁️  题目实时监控线程已启动")
            while self.monitor_running:
                try:
                    # 每2秒检测一次
                    time.sleep(2)
                    if not self.monitor_running:
                        break
                    # 检测题目弹窗
                    if self.check_for_quiz():
                        if not self.quiz_handling:
                            self.logger.info("🚨 [实时监控] 检测到题目弹窗，暂停主循环")
                            self.quiz_detected.set()  # 通知主线程暂停
                            self.quiz_handling = True
                            # 处理题目
                            self.answer_quiz()
                            self.quiz_handling = False
                            self.quiz_detected.clear()  # 清除事件，恢复主线程
                            self.logger.info("✅ [实时监控] 题目处理完毕，恢复主循环")
                except Exception as e:
                    self.logger.debug(f"题目监控线程异常: {e}")
                    continue
            self.logger.info("👁️  题目实时监控线程已停止")
        
        self.quiz_monitor_thread = threading.Thread(target=monitor_loop, daemon=True, name="QuizMonitor")
        self.quiz_monitor_thread.start()

    def stop_quiz_monitor(self):
        """停止题目监控线程"""
        self.monitor_running = False
        if self.quiz_monitor_thread and self.quiz_monitor_thread.is_alive():
            self.quiz_monitor_thread.join(timeout=5)

    def check_for_quiz(self):
        """检测是否出现题目弹窗"""
        try:
            dialogs = self.driver.find_elements(By.XPATH, "//div[contains(@class,'el-dialog__wrapper') and not(contains(@style,'display: none'))]")
            for d in dialogs:
                if d.is_displayed():
                    return True
            return False
        except Exception:
            return False

    def select_options_by_letters_v2(self, letters):
        """根据字母点击选项（支持多选，随机顺序与间隔，必要时二次点击确认）"""
        try:
            import random
            if isinstance(letters, str):
                letters = [letters]
            options = self.get_quiz_options()
            if not options:
                self.logger.debug("未找到可点击选项容器")
                return False
            # 构造按索引映射的字母序列（A,B,C...）
            index_to_letter = [chr(ord('A') + i) for i in range(len(options))]
            # 随机化点击顺序
            to_click = [l for l in letters if l in index_to_letter]
            random.shuffle(to_click)
            last_clicked = None
            for l in to_click:
                idx = ord(l) - ord('A')
                if 0 <= idx < len(options):
                    opt = options[idx]
                    try:
                        # 滚动到视图中再点击
                        try:
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", opt)
                        except Exception:
                            pass
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(self.driver)
                        actions.move_to_element(opt)
                        actions.click()
                        actions.perform()
                        last_clicked = opt
                        # 选项间隔（0.5-1.5秒）
                        self.smart_wait(random.uniform(0.5, 1.5))
                        # 每次点击后滚动到底，确保答案可见
                        self.scroll_quiz_dialog('bottom')
                    except Exception:
                        continue
            # 二次点击最后一个选项以确认（某些页面需要）
            if last_clicked is not None:
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    actions = ActionChains(self.driver)
                    actions.move_to_element(last_clicked)
                    actions.click()
                    actions.perform()
                    self.smart_wait(random.uniform(0.5, 1.0))
                except Exception:
                    pass
            return True
        except Exception as e:
            self.logger.debug(f"选择多选项失败: {e}")
            return False

    def answer_quiz(self):
        """处理题目弹窗：识别题型，滚动查看答案，并选择选项"""
        try:
            if not self.check_for_quiz():
                return False
            # 先滚动到底，避免答案不完整
            self.scroll_quiz_dialog('bottom')
            letters = self.extract_correct_answers()
            if not letters:
                # 单选题或答案未出现，滚动后重试
                self.scroll_quiz_dialog('bottom')
                letters = self.extract_correct_answers()
            # 获取选项列表
            options = self.get_quiz_options()
            if not options:
                self.logger.info("🔔 未检测到选项，请手动处理；程序继续监控")
                return False
            if letters:
                if self.is_multi_choice():
                    # 多选：随机顺序点击，并在每步间滚动
                    self.select_options_by_letters_v2(letters)
                else:
                    # 单选：点击第一个答案
                    first = letters[0]
                    self.click_correct_answer(first, options)
                    # 点击后再滚动一次以确认状态
                    self.scroll_quiz_dialog('bottom')
                # 作答完成后尝试关闭弹窗
                try:
                    self.logger.info("✅ 已完成作答，尝试关闭题目弹窗")
                    closed = self.close_quiz_dialog()
                    if not closed:
                        self.logger.info("🔔 自动关闭失败，请手动关闭；程序将继续监控")
                except Exception:
                    pass
                return True
            else:
                # 未识别出答案，等待人工介入
                self.logger.info("🔔 未识别到答案，请手动选择；程序将继续播放监控")
                return False
        except Exception as e:
            self.logger.debug(f"处理题目弹窗失败: {e}")
            return False

    def wait_for_video_complete(self, max_wait_minutes=60):
        """等待当前视频播放完成（带卡停检测）"""
        self.logger.info("⏰ 开始监控视频播放...")
        
        # 【反检测优化】检查间隔随机化，不再固定10秒
        import random
        check_interval = random.uniform(8, 15)  # 8-15秒随机间隔
        max_wait_time = max_wait_minutes * 60  # 最长等待时间（秒）
        elapsed_time = 0
        
        last_progress_check = 0  # 上次检查的进度
        no_progress_count = 0  # 连续无进展次数
        
        start_time = time.time()
        
        while elapsed_time < max_wait_time:
            # 【新增】检查是否有题目弹窗，如有则等待处理完成
            if self.quiz_detected.is_set():
                self.logger.debug("⏸️  主循环暂停，等待题目处理...")
                self.quiz_detected.wait()  # 阻塞，直到题目处理完毕
                self.logger.debug("▶️  主循环恢复")
                continue
            
            # 检查视频是否还在播放
            if not self.ensure_video_playing():
                self.logger.warning("⚠️  视频似乎已停止，尝试恢复播放")
                self.recover_stuck_video()
            
            # 检查进度是否卡住
            current_progress = self.get_video_progress()
            
            # 如果进度完全没有变化（差距小于1秒）
            if abs(current_progress - last_progress_check) < 1:
                no_progress_count += 1
                self.logger.warning(f"⚠️  视频进度无变化，连续{no_progress_count}次 ({current_progress:.0f}秒)")
                
                # 连续3次无进展就触发恢夏（防脚本机制）
                if no_progress_count >= 3:
                    self.logger.warning(f"🔧 连续{no_progress_count}次进度无变化，可能触发防脚本机制，尝试恢复...")
                    self.recover_stuck_video()
                    no_progress_count = 0  # 重置计数
            else:
                # 有进展，重置计数
                if no_progress_count > 0:
                    self.logger.info(f"✅ 视频恢复正常，进度: {current_progress:.0f}秒")
                no_progress_count = 0
            
            last_progress_check = current_progress
            
            # TODO: 添加视频完成检测逻辑
            # 可以通过检测视频总时长和当前进度来判断
            
            # 【反检测优化】每次等待后重新生成下次检查间隔
            self.smart_wait(check_interval)
            check_interval = random.uniform(8, 15)  # 下次检查间隔随机化
            elapsed_time = time.time() - start_time
            
            # 每分钟输出一次日志
            if int(elapsed_time) % 60 == 0 and elapsed_time > 0:
                self.logger.info(f"  已观看 {int(elapsed_time) // 60} 分钟... (当前进度: {current_progress:.0f}秒)")
        
        if elapsed_time >= max_wait_time:
            self.logger.warning(f"⚠️  达到最长等待时间 {max_wait_minutes} 分钟")
    
    def run(self):
        """运行自动播放程序"""
        try:
            self.logger.info("\n" + "="*60)
            self.logger.info("📋 任务开始 - 有题目课程模式")
            self.logger.info("="*60)
            
            # 清空本次任务的已完成视频记录
            self.progress['completed_videos'] = []
            self.save_progress()
            
            # 清空已观看视频列表（任务开始时重置）
            self.watched_video_list = []
            self.logger.info("✅ 已清空已观看视频列表")
            
            # 【新增】启动题目实时监控线程
            self.start_quiz_monitor()
            
            # 登录
            if not self.login():
                self.logger.warning("⚠️ 登录失败，等待用户手动登录...")
                waited = 0
                while waited < 600:
                    try:
                        current_url = self.driver.current_url
                        if "onlinestuh5" in current_url and "login" not in current_url:
                            self.logger.info("✅ 已检测到登录成功")
                            break
                    except Exception:
                        pass
                    time.sleep(2)
                    waited += 2
            
            # 【新增】检查是否有course_url，决定是否跳过课程查找
            if hasattr(self, 'course_url') and self.course_url:
                # 有URL，直接跳转
                self.logger.info(f"🌐 检测到course_url，直接跳转: {self.course_url}")
                self.logger.info("✅ 跳过课程查找步骤")
                try:
                    self.driver.get(self.course_url)
                    self.smart_wait(3)  # 等待页面加载
                    self.logger.info("✅ 已成功跳转到课程URL")
                    
                    # 处理常见弹窗（承诺书/学前必读/提示框）
                    try:
                        candidates = [
                            "//button[contains(@class,'agree-btn')]",
                            "//button[contains(@class,'btn') and (contains(.,'同意') or contains(.,'确认') or contains(.,'知道了') or contains(.,'我知道了'))]",
                            "//span[contains(.,'同意')]/ancestor::button",
                            "//*[@role='dialog']//button[contains(.,'同意') or contains(.,'确认') or contains(.,'知道了')]",
                            "//i[contains(@class,'iconguanbi')]"
                        ]
                        for xpath in candidates:
                            elems = self.driver.find_elements(By.XPATH, xpath)
                            if elems:
                                try:
                                    elems[0].click()
                                    self.smart_wait(1)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    
                    # 等待课程页面或用户处理未知弹窗
                    self.logger.info("🔔 如有弹窗或未知提示，请手动处理；程序将等待进入课程页面...")
                    waited = 0
                    while waited < 600:
                        try:
                            if "studyvideo" in self.driver.current_url or self.driver.find_elements(By.TAG_NAME, "video"):
                                self.logger.info("✅ 已进入课程页面")
                                break
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
                        time.sleep(2)
                        waited += 2
                except Exception as e:
                    self.logger.error(f"❌ 跳转到课程URL失败: {e}")
                    self.logger.info("🔔 请手动进入课程页面，程序将等待...")
                    waited = 0
                    while waited < 600:
                        try:
                            if "studyvideo" in self.driver.current_url or self.driver.find_elements(By.TAG_NAME, "video"):
                                self.logger.info("✅ 已进入课程页面")
                                break
                        except Exception:
                            pass
                        time.sleep(2)
                        waited += 2
                
                # 跳过enter_study_page，因为已经在课程页面了
            else:
                # 没有URL，使用传统的课程查找
                # 查找并进入课程
                if not self.find_course():
                    self.logger.warning("⚠️ 未找到课程，等待用户手动进入课程页面...")
                    waited = 0
                    while waited < 600:
                        try:
                            if "studyvideo" in self.driver.current_url or self.driver.find_elements(By.TAG_NAME, "video"):
                                self.logger.info("✅ 已进入课程页面")
                                break
                        except Exception:
                            pass
                        time.sleep(2)
                        waited += 2
                else:
                    # 进入学习页面
                    if not self.enter_study_page():
                        self.logger.warning("⚠️ 进入学习页面失败，等待用户手动进入课程页面...")
                        waited = 0
                        while waited < 600:
                            try:
                                if "studyvideo" in self.driver.current_url or self.driver.find_elements(By.TAG_NAME, "video"):
                                    self.logger.info("✅ 已进入课程页面")
                                    break
                            except Exception:
                                pass
                            time.sleep(2)
                            waited += 2
            
            # 查找未观看的视频
            # 弹窗安全处理：尝试关闭，失败则等待人工处理
            try:
                self.close_all_dialogs()
            except Exception:
                pass
            dialogs = []
            try:
                dialogs = self.driver.find_elements(By.XPATH, "//*[@role='dialog' or contains(@class,'dialog') or contains(@class,'el-dialog__wrapper')]")
            except Exception:
                dialogs = []
            if dialogs:
                self.logger.info("🔔 检测到弹窗，请手动关闭；程序将等待进入播放页面...")
                waited = 0
                while waited < 600:
                    try:
                        if self.driver.find_elements(By.TAG_NAME, 'video'):
                            break
                    except Exception:
                        pass
                    time.sleep(2)
                    waited += 2
            unwatched_videos = self.find_unwatched_videos()
            
            if not unwatched_videos:
                self.logger.warning("⚠️  未找到未观看的视频，直接监控题目弹窗")
            else:
                self.logger.info(f"🎯 找到 {len(unwatched_videos)} 个未观看视频，开始播放")
                
                # 播放第一个未观看视频
                first_video = unwatched_videos[0]
                self.logger.info(f"🎬 点击播放: {first_video['text']}")
                
                try:
                    # 尝试点击
                    first_video['element'].click()
                    self.logger.info("✅ 普通点击成功")
                except:
                    try:
                        # 如果普通点击失败，尝试ActionChains点击
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(self.driver)
                        actions.move_to_element(first_video['element'])
                        actions.click()
                        actions.perform()
                        self.logger.info("✅ ActionChains点击成功")
                    except Exception as e:
                        self.logger.error(f"❌ 点击视频失败: {e}")
                        # 等待人工介入：请手动点击右侧目录或视频中央开始播放
                        self.logger.info("🔔 请手动点击开始播放或关闭弹窗，程序将等待...")
                        waited_manual = 0
                        while waited_manual < 600:
                            try:
                                # 视频元素出现且处于播放状态
                                video_element = self.driver.find_elements(By.TAG_NAME, 'video')
                                if video_element:
                                    is_playing = self.driver.execute_script("return document.querySelector('video') ? !document.querySelector('video').paused : false")
                                    if is_playing:
                                        self.logger.info("✅ 检测到视频已开始播放")
                                        break
                            except Exception:
                                pass
                            time.sleep(2)
                            waited_manual += 2
                
                self.smart_wait(3)  # 等待视频加载
                
                # 【改进】点击视频中央区域启动播放（避免被检测）
                self.logger.info("🎯 点击视频中央区域启动播放...")
                try:
                    # 查找video元素并点击中央（添加随机偏移）
                    video_element = self.driver.find_element(By.TAG_NAME, 'video')
                    if video_element:
                        # 获取视频元素的位置和大小
                        location = video_element.location
                        size = video_element.size
                        
                        # 计算中心点
                        center_x = location['x'] + size['width'] // 2
                        center_y = location['y'] + size['height'] // 2
                        
                        # 添加随机偏移（±50像素）
                        import random
                        offset_x = random.randint(-50, 50)
                        offset_y = random.randint(-50, 50)
                        
                        target_x = center_x + offset_x
                        target_y = center_y + offset_y
                        
                        self.logger.info(f"📍 视频中心坐标: ({center_x}, {center_y})")
                        self.logger.info(f"📍 随机偏移: ({offset_x:+d}, {offset_y:+d}) 像素")
                        self.logger.info(f"📍 实际点击坐标: ({target_x}, {target_y})")
                        
                        # 使用ActionChains点击指定坐标
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(self.driver)
                        # 移动到视频元素
                        actions.move_to_element_with_offset(video_element, offset_x, offset_y)
                        actions.click()
                        actions.perform()
                        
                        self.logger.info("✅ 已点击视频区域（含随机偏移）")
                        self.smart_wait(2)
                    else:
                        self.logger.warning("⚠️  未找到video元素")
                        
                except Exception as e:
                    self.logger.warning(f"⚠️  点击视频失败: {e}，继续监控")
            
            # 【改进】主循环：每次播完一个视频后重新查找下一个
            self.logger.info("\n" + "="*60)
            self.logger.info("🎬 开始自动播放（每次播完后重新查找下一个）")
            self.logger.info("="*60)
            
            videos_played = 0
            attempt = 0
            max_videos = 200  # 最多尝试200个视频
            # 使用已经查找到的视频列表（避免第一轮重复查找）
            # unwatched_videos 已经在上面的 find_unwatched_videos() 中填充
            
            while attempt < max_videos:
                attempt += 1
                self.logger.info(f"\n=== 第 {attempt} 轮播放 ===")
                
                # 智能刷新：每10次查找前刷新一次页面
                if self.items_processed_since_refresh >= self.refresh_interval:
                    self.logger.info(f"已处理{self.items_processed_since_refresh}个项目，刷新页面以更新状态...")
                    self.driver.refresh()
                    self.smart_wait(3)
                    self.items_processed_since_refresh = 0
                    unwatched_videos = []  # 清空缓存
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
                video_to_play = unwatched_videos.pop(0)
                self.logger.info(f"🎬 开始播放: {video_to_play['text'][:50]}")
                
                # 点击视频
                try:
                    video_to_play['element'].click()
                    self.logger.info("✅ 普通点击成功")
                except:
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(self.driver)
                        actions.move_to_element(video_to_play['element'])
                        actions.click()
                        actions.perform()
                        self.logger.info("✅ ActionChains点击成功")
                    except Exception as e:
                        self.logger.error(f"❌ 点击视频失败: {e}")
                        continue
                
                self.smart_wait(3)
                
                # 【改进】点击视频中央区域启动播放（避免被检测）
                self.logger.info("🎯 点击视频中央区域启动播放...")
                try:
                    # 查找video元素并点击中央（添加随机偏移）
                    video_element = self.driver.find_element(By.TAG_NAME, 'video')
                    if video_element:
                        # 获取视频元素的位置和大小
                        location = video_element.location
                        size = video_element.size
                        
                        # 计算中心点
                        center_x = location['x'] + size['width'] // 2
                        center_y = location['y'] + size['height'] // 2
                        
                        # 添加随机偏移（±50像素）
                        import random
                        offset_x = random.randint(-50, 50)
                        offset_y = random.randint(-50, 50)
                        
                        target_x = center_x + offset_x
                        target_y = center_y + offset_y
                        
                        self.logger.info(f"📍 视频中心坐标: ({center_x}, {center_y})")
                        self.logger.info(f"📍 随机偏移: ({offset_x:+d}, {offset_y:+d}) 像素")
                        self.logger.info(f"📍 实际点击坐标: ({target_x}, {target_y})")
                        
                        # 使用ActionChains点击指定坐标
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(self.driver)
                        # 移动到视频元素
                        actions.move_to_element_with_offset(video_element, offset_x, offset_y)
                        actions.click()
                        actions.perform()
                        
                        self.logger.info("✅ 已点击视频区域（含随机偏移）")
                        self.smart_wait(2)
                    else:
                        self.logger.warning("⚠️  未找到video元素")
                        
                except Exception as e:
                    self.logger.warning(f"⚠️  点击视频失败: {e}，继续监控")
                
                # 监控视频播放并回答题目
                self.logger.info("⏰ 开始监控视频播放...")
                
                check_interval_seconds = 10  # 每10秒检查一次
                max_wait_time = 60 * 60  # 最长等待1小时
                elapsed_time = 0
                
                last_progress_check = 0
                no_progress_count = 0
                
                video_completed = False
                current_title = None
                
                # 【新增】记录本次视频开始时的累计播放时间
                video_start_total_time = self.total_watch_time_seconds
                
                while elapsed_time < max_wait_time:
                    # 检查是否有题目弹窗
                    if self.check_for_quiz():
                        self.answer_quiz()
                    
                    # 【优化】获取视频进度和时长，用于判断是否接近结束
                    current_progress = self.get_video_progress()
                    try:
                        video_duration = self.driver.execute_script(
                            "return document.querySelector('video') ? document.querySelector('video').duration : 0"
                        )
                        # 计算播放进度百分比
                        progress_percentage = (current_progress / video_duration * 100) if video_duration > 0 else 0
                    except:
                        video_duration = 0
                        progress_percentage = 0
                    
                    # 【优化】只在视频进度低于95%时才检查卡停
                    if progress_percentage < 95:
                        # 检查视频是否还在播放
                        if not self.ensure_video_playing():
                            self.logger.warning("⚠️  视频似乎已停止，尝试恢复播放")
                            self.recover_stuck_video()
                    else:
                        self.logger.debug(f"🎯 视频已接近结束 ({progress_percentage:.1f}%)，跳过卡停检测")
                    # 检查进度是否卡住
                    if abs(current_progress - last_progress_check) < 1:
                        no_progress_count += 1
                        self.logger.warning(f"⚠️  视频进度无变化，连续{no_progress_count}次 ({current_progress:.0f}秒)")
                        
                        # 【优化】只在进度低于95%时才尝试恢复
                        if no_progress_count >= 3 and progress_percentage < 95:
                            self.logger.warning(f"🔧 连续{no_progress_count}次进度无变化，可能触发防脚本机制，尝试恢复...")
                            self.recover_stuck_video()
                            self.smart_wait(2)
                            no_progress_count = 0
                        elif progress_percentage >= 95:
                            self.logger.debug(f"🎯 视频已接近结束 ({progress_percentage:.1f}%)，跳过恢复操作，等待自然结束")
                    else:
                        if no_progress_count > 0:
                            self.logger.info(f"✅ 视频恢复正常，进度: {current_progress:.0f}秒")
                        no_progress_count = 0
                    
                    last_progress_check = current_progress
                    
                    # 【新版】检查视频是否播放完成（基于视频播放进度）
                    try:
                        # 获取视频时长和当前进度
                        video_info = self.driver.execute_script("""
                            var video = document.querySelector('video');
                            if (video) {
                                return {
                                    duration: video.duration,
                                    currentTime: video.currentTime,
                                    ended: video.ended
                                };
                            }
                            return null;
                        """)
                        
                        if video_info:
                            duration = video_info.get('duration', 0)
                            currentTime = video_info.get('currentTime', 0)
                            ended = video_info.get('ended', False)
                            
                            # 检测视频是否播放完成
                            # 1. 视频ended属性为true
                            # 2. 当前进度距离总时长不到5秒（避免卡顿误判）
                            # 【优化】记录检测到的时长信息
                            if duration > 0:
                                self.logger.debug(f"📊 视频时长信息: 总时长={duration:.0f}秒, 当前={currentTime:.0f}秒, 进度={currentTime/duration*100:.1f}%")
                            
                            if ended or (duration > 0 and currentTime >= duration - 5):
                                self.logger.info(f"✅ 检测到视频播放完成: {currentTime:.0f}/{duration:.0f}秒")
                                
                                # 【新增】累加本次视频的实际播放时长
                                video_watch_time = currentTime
                                self.total_watch_time_seconds += video_watch_time
                                total_minutes = self.total_watch_time_seconds / 60
                                self.logger.info(f"📊 本次视频播放: {video_watch_time:.0f}秒 ({video_watch_time/60:.1f}分钟)")
                                self.logger.info(f"📊 已播放时间: {total_minutes:.1f}分钟 ({self.total_watch_time_seconds:.0f}秒)")
                                
                                video_completed = True
                                break
                            else:
                                self.logger.debug(f"视频播放中: {currentTime:.0f}/{duration:.0f}秒 ({currentTime/duration*100:.1f}%)")
                    except Exception as e:
                        self.logger.debug(f"检测视频完成状态失败: {e}")
                    
                    # 等待10秒
                    time.sleep(10)
                    elapsed_time += 10
                    
                    # 显示进度
                    # 【优化】同时显示视频总时长和已播放时间（包含当前视频已播放部分）
                    try:
                        video_duration = self.driver.execute_script(
                            "return document.querySelector('video') ? document.querySelector('video').duration : 0"
                        )
                        # 【修改】已播放时间 = 已完成视频的累计时长 + 当前视频已播放时长
                        total_minutes = (self.total_watch_time_seconds + current_progress) / 60
                        if video_duration and video_duration > 0:
                            self.logger.info(f"播放进度: {current_progress:.0f}秒 | 等待时间: {int(elapsed_time)}秒 | 视频总长: {video_duration:.0f}秒 | 已播放时间: {total_minutes:.1f}分钟")
                        else:
                            self.logger.info(f"播放进度: {current_progress:.0f}秒 | 等待时间: {int(elapsed_time)}秒 | 已播放时间: {total_minutes:.1f}分钟")
                    except:
                        total_minutes = (self.total_watch_time_seconds + current_progress) / 60
                        self.logger.info(f"播放进度: {current_progress:.0f}秒 | 等待时间: {int(elapsed_time)}秒 | 已播放时间: {total_minutes:.1f}分钟")
                
                if video_completed:
                    videos_played += 1
                    self.items_processed_since_refresh += 1
                    self.logger.info(f"✅ 成功播放第 {videos_played} 个视频")
                    
                    # 记录已观看视频
                    if current_title and current_title not in self.progress['completed_videos']:
                        self.progress['completed_videos'].append(current_title)
                        self.progress['total_watched'] += 1
                        self.save_progress()
                    
                    # 【新增】检查是否达到预设观看时间
                    if self.max_watch_minutes > 0:
                        total_minutes = self.total_watch_time_seconds / 60
                        if total_minutes >= self.max_watch_minutes:
                            self.logger.info("\n" + "="*60)
                            self.logger.info(f"✅ 已达到预设观看时间 {self.max_watch_minutes} 分钟")
                            self.logger.info(f"✅ 已播放时间: {total_minutes:.1f} 分钟 ({self.total_watch_time_seconds:.0f} 秒)")
                            self.logger.info(f"✅ 本次播放 {videos_played} 个视频")
                            self.logger.info("="*60)
                            self.logger.info("🚫 结束播放并退出程序")
                            return  # 直接退出run方法，结束程序
                else:
                    self.logger.warning(f"⚠️  视频未检测到完成标记，可能超时")
                
                # 随机延迟
                import random
                delay = random.uniform(5, 10)
                self.smart_wait(delay)
            
            # 显示最终统计
            self.logger.info("\n" + "="*60)
            if videos_played > 0:
                self.logger.info(f"✅ 自动播放程序完成，本次播放 {videos_played} 个视频")
            else:
                self.logger.info("✅ 所有视频已播放完成，无需播放")
            self.logger.info(f"✅ 总计已观看: {self.progress['total_watched']} 个视频")
            self.logger.info("="*60)
            
        except KeyboardInterrupt:

            
            # 由于是自动连续播放，这里主要是监控题目弹窗和重复播放
            while True:
                self.smart_wait(5)
                
                # 检查题目弹窗
                if self.check_for_quiz():
                    self.answer_quiz()
                
                # 定时检查是否重复播放已观看视频
                check_counter += 1
                if check_counter >= check_interval:
                    self.logger.debug("🔍 定时检查是否重复播放...")
                    if self.check_and_skip_watched_video():
                        self.logger.info("✅ 已跳转到下一个未观看视频")
                    check_counter = 0  # 重置计数器
                
                # TODO: 添加退出条件（如达到观看时长、所有视频播放完毕等）
            
        except KeyboardInterrupt:
            self.logger.info("\n\n⚠️  用户中断程序")
        except Exception as e:
            self.logger.error(f"\n\n❌ 程序异常: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        finally:
            self.cleanup()
    
    def cleanup(self):
        """清理资源（关闭时调用）"""
        # 【新增】停止题目监控线程
        try:
            self.stop_quiz_monitor()
        except Exception:
            pass
        
        # 【优先级最高】关闭浏览器（确保不被中断）
        if hasattr(self, 'driver'):
            try:
                self.driver.quit()
                print("✅ 浏览器已关闭")  # 使用print确保显示
            except Exception as e:
                print(f"关闭浏览器失败: {e}")
        
        # 以下操作可能被中断，但不影响浏览器关闭
        try:
            # 清空已观看视频列表
            if hasattr(self, 'watched_video_list'):
                self.watched_video_list = []
                if hasattr(self, 'logger'):
                    self.logger.debug("✅ 已清空已观看视频列表")
            
            if hasattr(self, 'logger'):
                self.logger.info("\n" + "="*60)
                self.logger.info("📊 本次运行统计")
                self.logger.info("="*60)
                self.logger.info(f"回答题目数: {self.quizzes_answered_this_session}")
                
                # 安全访问progress
                if hasattr(self, 'progress') and self.progress:
                    self.logger.info(f"总计回答题目: {self.progress.get('total_quizzes', 0)}")
                
                self.logger.info("="*60)
            
            # 保存进度
            if hasattr(self, 'progress'):
                self.save_progress()
            
            # 【新增】关闭时清理日志（可能被中断，但不影响浏览器关闭）
            if hasattr(self, 'logger'):
                self.logger.info("🧹 检查并清理日志文件...")
            self.check_and_cleanup_logs()
            
        except KeyboardInterrupt:
            print("⚠️  清理过程被中断，但浏览器已关闭")
        except Exception as e:
            print(f"清理过程异常: {e}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='知到网页版自动播放器 - 有题目版本')
    parser.add_argument('--account', type=str, default='account.json', help='账号配置文件')
    parser.add_argument('--headless', action='store_true', help='无头模式')
    
    args = parser.parse_args()
    
    player = ZhidaoWebAutoPlayerWithQuiz(account_file=args.account, headless=args.headless)
    player.run()


if __name__ == '__main__':
    main()

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

知到网页版自动播放脚本 - 纯答题模式
支持课程测试、章节测试等答题功能，集成DeepSeek API智能答题
"""

import time
import json
import os
import sys
import random
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains


class ZhidaoQuizOnlyPlayer:
    """知到网页版自动播放器 - 纯答题模式"""
    
    def __init__(self, account_file='account.json', headless=False):
        """初始化播放器"""
        self.account_file = account_file
        
        # 加载配置
        self.config = self.load_config()
        self.account_config = self.load_account_config()
        
        # 【重要】先设置日志，因为后续方法会使用logger
        self.setup_logging()
        
        # 加载进度
        self.progress = self.load_progress()
        
        # 【新增】加载环境变量
        load_dotenv()
        
        # 【优化】DeepSeek API配置 - 优先使用用户配置，否则从环境变量加载
        self.api_key = self.account_config.get('deepseek_api_key', '').strip()
        self.api_base_url = None
        self.api_model = None
        
        if not self.api_key:
            # 尝试从系统环境变量加载
            self.api_key = os.getenv('ANTHROPIC_AUTH_TOKEN', '').strip()
            self.api_base_url = os.getenv('ANTHROPIC_BASE_URL', '').strip()
            self.api_model = os.getenv('ANTHROPIC_MODEL', 'deepseek-reasoner').strip()
            
            if self.api_key:
                self.logger.info("✅ 从系统环境变量加载API配置成功")
                self.logger.info(f"📡 API Base URL: {self.api_base_url}")
                self.logger.info(f"🤖 API Model: {self.api_model}")
            else:
                self.logger.warning("⚠️  未配置API密钥（账号配置和环境变量均未找到），答题功能将受限")
        else:
            self.logger.info("✅ 使用账号配置文件中的API密钥")
            # 用户自定义API，使用默认配置
            self.api_base_url = self.account_config.get('api_base_url', 'https://api.deepseek.com').strip()
            self.api_model = self.account_config.get('api_model', 'deepseek-chat').strip()
        
        # 【新增】验证API连接
        if self.api_key:
            if not self.verify_api_connection():
                self.logger.error("❌ API连接验证失败，程序退出")
                self.logger.error("请检查以下配置：")
                self.logger.error(f"  - API密钥是否正确")
                self.logger.error(f"  - API Base URL: {self.api_base_url}")
                self.logger.error(f"  - 网络连接是否正常")
                sys.exit(1)  # 退出程序
        
        # 初始化浏览器
        self.setup_driver(headless)
        
        # 答题统计
        self.questions_answered = 0
        self.questions_total = 0
        
        self.logger.info("="*60)
        self.logger.info("知到网页版自动播放器 - 纯答题模式 v1.0")
        self.logger.info("="*60)
    
    def setup_logging(self):
        """设置日志系统"""
        # 获取项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # 从account文件名提取账号编号
        account_filename = os.path.basename(self.account_file)
        account_num = account_filename.replace('account', '').replace('.json', '')
        if not account_num:
            account_num = '1'
        
        log_file = os.path.join(project_root, 'log', f'zhidao_account{account_num}_quiz_only.log')
        
        # 配置日志
        self.logger = logging.getLogger(f'ZhidaoQuizOnly_{account_num}')
        self.logger.setLevel(logging.INFO)
        
        # 清除已有的处理器
        self.logger.handlers.clear()
        
        # 文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 格式化
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def load_config(self):
        """加载全局配置"""
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(project_root, '启动', 'config.json')
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                "captcha_timeout": 300,
                "enable_notifications": True
            }
    
    def load_account_config(self):
        """加载账号配置"""
        with open(self.account_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def load_progress(self):
        """加载进度记录"""
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        account_filename = os.path.basename(self.account_file)
        account_num = account_filename.replace('account', '').replace('.json', '')
        if not account_num:
            account_num = '1'
        
        progress_file = os.path.join(project_root, 'log', f'progress_account{account_num}.json')
        
        if os.path.exists(progress_file):
            try:
                with open(progress_file, 'r', encoding='utf-8-sig') as f:
                    progress = json.load(f)
                    
                    # 确保必要的键存在
                    if 'completed_quizzes' not in progress:
                        progress['completed_quizzes'] = []
                    if 'total_questions_answered' not in progress:
                        progress['total_questions_answered'] = 0
                    
                    return progress
            except json.JSONDecodeError as e:
                self.logger.warning(f"⚠️  进度文件解析失败: {e}")
                
        return {
            'completed_quizzes': [],
            'total_questions_answered': 0,
            'last_run': None
        }
    
    def save_progress(self):
        """保存进度记录"""
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
        """设置Chrome浏览器驱动"""
        chrome_options = Options()
        
        if headless:
            chrome_options.add_argument('--headless')
        
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1349,768')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        # 禁用自动化提示
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            try:
                self.logger.info("尝试使用webdriver-manager自动下载ChromeDriver...")
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                self.logger.info("✅ 使用webdriver-manager初始化成功")
            except Exception as download_error:
                self.logger.warning(f"⚠️  webdriver-manager下载失败: {str(download_error)[:100]}")
                self.logger.info("🔄 尝试使用系统环境中的ChromeDriver...")
                
                self.driver = webdriver.Chrome(options=chrome_options)
                self.logger.info("✅ 使用系统 ChromeDriver 初始化成功")

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
    
    def login(self):
        """登录知到网站"""
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
                
                # 查找用户名输入框
                username_input = None
                username_selectors = [
                    "//input[@type='text']",
                    "//input[@placeholder='手机号']",
                ]
                
                for selector in username_selectors:
                    try:
                        username_input = self.wait.until(EC.presence_of_element_located((By.XPATH, selector)))
                        break
                    except:
                        continue
                
                if username_input:
                    username_input.clear()
                    username_input.send_keys(username)
                    self.logger.info("已输入用户名")
                    self.smart_wait(1)
                
                # 查找密码输入框
                password_input = None
                password_selectors = [
                    "//input[@type='password']",
                ]
                
                for selector in password_selectors:
                    try:
                        password_input = self.wait.until(EC.presence_of_element_located((By.XPATH, selector)))
                        break
                    except:
                        continue
                
                if password_input:
                    password_input.clear()
                    password_input.send_keys(password)
                    self.logger.info("已输入密码")
                    self.smart_wait(1)
                
                # 查找登录按钮
                login_btn = None
                login_selectors = [
                    "//button[contains(text(), '登录')]",
                    "//span[contains(text(), '登录')]",
                ]
                
                for selector in login_selectors:
                    try:
                        elements = self.driver.find_elements(By.XPATH, selector)
                        for elem in elements:
                            if '登录' in elem.text:
                                login_btn = elem
                                break
                        if login_btn:
                            break
                    except:
                        continue
                
                if login_btn:
                    login_btn.click()
                    self.logger.info("已点击登录按钮")
                    self.smart_wait(3)
                
                # 【新增】等待并持续检测登录状态（最多30秒）
                max_wait = 30
                check_interval = 2
                elapsed = 0
                captcha_detected = False  # 【新增】标记是否检测到人机验证
                
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
                        captcha_detected = True  # 【新增】设置标记
                        break
                    
                    # 检查登录是否成功
                    if self.check_login_success():
                        self.logger.info("登录成功！")
                        self.logger.info("⏳ 等待10秒，确保页面完全加载且无第二次人机验证...")
                        time.sleep(10)  # 【修改】5秒改为10秒，防止多重人机验证
                        
                        # 再次检查是否有新的人机验证
                        if self.check_captcha():
                            self.logger.warning("⚠️  检测到第二次人机验证！")
                            if not self.wait_for_captcha_completion():
                                self.logger.warning("第二次人机验证等待超时或失败")
                                return False
                            self.logger.info("✅ 第二次人机验证已完成")
                            # 再等待10秒确认没有第三次验证
                            time.sleep(10)
                        
                        self.logger.info("✅ 页面加载完成，继续执行")
                        return True
                    
                    # 检查是否还在登录页面
                    current_url = self.driver.current_url
                    if "login" not in current_url.lower():
                        self.logger.info("已离开登录页面，检查最终状态...")
                        self.smart_wait(2)
                        if self.check_login_success():
                            self.logger.info("登录成功！")
                            self.logger.info("⏳ 等待10秒，确保页面完全加载且无第二次人机验证...")
                            time.sleep(10)
                            
                            # 再次检查是否有新的人机验证
                            if self.check_captcha():
                                self.logger.warning("⚠️  检测到第二次人机验证！")
                                if not self.wait_for_captcha_completion():
                                    self.logger.warning("第二次人机验证等待超时或失败")
                                    return False
                                self.logger.info("✅ 第二次人机验证已完成")
                                time.sleep(10)
                            
                            self.logger.info("✅ 页面加载完成，继续执行")
                            return True
                
                # 【新增】如果是因为人机验证完成而break，需要再次检查登录状态
                if captcha_detected:
                    self.logger.info("人机验证已完成，检查登录状态...")
                    self.logger.info("⏳ 等待10秒，确保页面完全加载且无第二次人机验证...")
                    time.sleep(10)
                    
                    # 再次检查是否有新的人机验证
                    if self.check_captcha():
                        self.logger.warning("⚠️  检测到第二次人机验证！")
                        if not self.wait_for_captcha_completion():
                            self.logger.warning("第二次人机验证等待超时或失败")
                            return False
                        self.logger.info("✅ 第二次人机验证已完成")
                        time.sleep(10)
                    
                    # 检查登录是否成功
                    if self.check_login_success():
                        self.logger.info("✅ 登录成功！")
                        self.logger.info("✅ 页面加载完成，继续执行")
                        return True
                    else:
                        self.logger.warning("⚠️  人机验证后登录状态仍未确认，继续检查...")
                
                self.logger.warning(f"等待{max_wait}秒后登录状态仍未确认")
                # 最后再检查一次
                if self.check_login_success():
                    self.logger.info("最终检查：登录成功！")
                    self.logger.info("⏳ 等待10秒，确保页面完全加载...")
                    time.sleep(10)
                    self.logger.info("✅ 页面加载完成，继续执行")
                    return True
                else:
                    self.logger.warning("最终检查：登录状态不确定")
                    return False
            else:
                self.logger.info("当前已登录或无需登录")
                self.logger.info("⏳ 等待10秒，确保页面完全加载...")
                time.sleep(10)
                self.logger.info("✅ 页面加载完成，继续执行")
                return True

        except Exception as e:
            self.logger.error(f"登录过程中出现错误: {e}")
            return False
    
    def cleanup(self):
        """清理资源"""
        try:
            if hasattr(self, 'driver'):
                self.driver.quit()
                self.logger.info("浏览器已关闭")
        except Exception as e:
            self.logger.error(f"清理资源失败: {e}")
    
    def check_captcha(self):
        """检查是否存在人机验证"""
        try:
            page_source = self.driver.page_source
            # 检查常见的人机验证关键词
            captcha_keywords = [
                'captcha',
                '验证码',
                '人机验证',
                '点击验证',
                '滑动验证',
                'geetest',
                'verify',
            ]
            
            for keyword in captcha_keywords:
                if keyword in page_source.lower():
                    return True
            
            return False
        except Exception as e:
            self.logger.error(f"检查人机验证时出错: {e}")
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
    
    def verify_api_connection(self):
        """验证DeepSeek API连接"""
        try:
            self.logger.info("\n" + "="*60)
            self.logger.info("🔍 验证DeepSeek API连接...")
            self.logger.info("="*60)
            
            # 构造简单的测试请求
            url = f"{self.api_base_url}/v1/chat/completions"
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            data = {
                'model': self.api_model,
                'messages': [
                    {
                        'role': 'user',
                        'content': '今天是几月几日星期几？请简洁回答。'
                    }
                ],
                'max_tokens': 50
            }
            
            self.logger.info(f"📡 请求URL: {url}")
            self.logger.info(f"🤖 使用模型: {self.api_model}")
            self.logger.info(f"💬 发送问题: 今天是几月几日星期几？")
            
            # 发送测试请求
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            # 检查响应
            if response.status_code == 200:
                result = response.json()
                
                if 'choices' in result and len(result['choices']) > 0:
                    message = result['choices'][0].get('message', {})
                    # 【修改】先尝试获取content，如果为空则获取reasoning_content
                    reply = message.get('content', '').strip()
                    reasoning = message.get('reasoning_content', '').strip()
                    
                    # 如果content为空但reasoning_content有内容，使用reasoning_content
                    if not reply and reasoning:
                        reply = reasoning
                        self.logger.info(f"🧠 DeepSeek推理模式，使用reasoning_content")
                    
                    self.logger.info(f"✅ API连接成功！")
                    if reply:
                        self.logger.info(f"💬 AI回答: {reply}")
                        # 验证回答是否合理
                        from datetime import datetime
                        now = datetime.now()
                        weekdays = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
                        current_weekday = weekdays[now.weekday()]
                        expected_date = f"{now.month}月{now.day}日"
                        if str(now.month) in reply or str(now.day) in reply or current_weekday in reply:
                            self.logger.info(f"✅ AI回答正确（期望包含: {expected_date} {current_weekday}）")
                        else:
                            self.logger.warning(f"⚠️  AI回答可能不准确（期望: {expected_date} {current_weekday}）")
                    else:
                        self.logger.warning(f"⚠️  API回复为空，但连接成功")
                        self.logger.info(f"📊 消息结构: {message}")
                    self.logger.info("="*60 + "\n")
                    return True
                else:
                    self.logger.error("❌ API返回格式异常")
                    self.logger.error(f"响应内容: {result}")
                    return False
            else:
                self.logger.error(f"❌ API请求失败，状态码: {response.status_code}")
                self.logger.error(f"错误信息: {response.text}")
                return False
            
        except requests.exceptions.Timeout:
            self.logger.error("❌ API请求超时（30秒）")
            self.logger.error("⚠️  请检查网络连接或API地址是否正确")
            return False
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ API请求异常: {e}")
            self.logger.error("⚠️  请检查API密钥和Base URL是否正确")
            return False
        except Exception as e:
            self.logger.error(f"❌ API验证过程出错: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def find_and_enter_quiz(self):
        """查找并进入测试"""
        try:
            quiz_type = self.account_config.get('quiz_type', '课程测试')
            course_name = self.account_config.get('course_name', '')
            
            self.logger.info(f"🔍 开始查找测试: {quiz_type}")
            self.logger.info(f"📚 课程名称: {course_name}")
            
            # 等待页面加载
            self.smart_wait(3)
            
            # 先尝试查找课程
            if course_name:
                self.logger.info(f"正在查找课程: {course_name}")
                if not self.find_and_enter_course(course_name):
                    self.logger.warning("⚠️  未找到指定课程，尝试直接查找测试")
            
            # 查找测试入口
            quiz_found = self.find_quiz_entrance(quiz_type)
            
            if quiz_found:
                self.logger.info(f"✅ 找到测试: {quiz_type}")
                
                # 检查是否已完成
                if self.check_quiz_completed():
                    self.logger.info("ℹ️  该测试已完成，跳过")
                    return False
                
                # 进入测试
                if self.enter_quiz():
                    self.logger.info("✅ 成功进入答题页面")
                    self.smart_wait(3)
                    return True
                else:
                    self.logger.error("❌ 进入测试失败")
                    return False
            else:
                self.logger.error(f"❌ 未找到测试: {quiz_type}")
                return False
                
        except Exception as e:
            self.logger.error(f"查找测试过程出错: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def find_and_enter_course(self, course_name):
        """查找并进入指定课程"""
        try:
            # 查找课程的多种选择器
            course_selectors = [
                f"//div[contains(text(), '{course_name}')]",
                f"//span[contains(text(), '{course_name}')]",
                f"//a[contains(text(), '{course_name}')]",
                f"//h3[contains(text(), '{course_name}')]",
                f"//h4[contains(text(), '{course_name}')]",
            ]
            
            course_element = None
            for selector in course_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for elem in elements:
                        if course_name in elem.text:
                            course_element = elem
                            self.logger.info(f"找到课程元素: {elem.text[:50]}")
                            break
                    if course_element:
                        break
                except Exception as e:
                    continue
            
            if course_element:
                # 使用ActionChains点击课程
                actions = ActionChains(self.driver)
                actions.move_to_element(course_element)
                actions.click()
                actions.perform()
                
                self.logger.info(f"✅ 已点击进入课程: {course_name}")
                self.smart_wait(3)
                return True
            else:
                self.logger.warning(f"⚠️  未找到课程: {course_name}")
                return False
                
        except Exception as e:
            self.logger.error(f"进入课程失败: {e}")
            return False
    
    def find_quiz_entrance(self, quiz_type):
        """查找测试入口"""
        try:
            self.logger.info(f"正在查找测试入口: {quiz_type}")
            
            # 【优化】根据实际页面结构调整选择器
            # 先切换到"作业考试"tab
            self.switch_to_exam_tab()
            
            # 测试入口的多种选择器（按优先级）
            quiz_selectors = [
                # 知到平台专用选择器
                "//div[contains(@class, 'homework-item')]",
                "//div[contains(@class, 'exam-item')]",
                "//div[contains(@class, 'test-item')]",
                # 通用选择器
                f"//div[contains(text(), '{quiz_type}')]",
                f"//span[contains(text(), '{quiz_type}')]",
                f"//a[contains(text(), '{quiz_type}')]",
                f"//button[contains(text(), '{quiz_type}')]",
                f"//li[contains(text(), '{quiz_type}')]",
                # 通用测试关键词
                "//div[contains(text(), '测试')]",
                "//span[contains(text(), '测试')]",
                "//a[contains(text(), '测试')]",
            ]
            
            self.quiz_element = None
            self.quiz_container = None
            
            for selector in quiz_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for elem in elements:
                        # 精确匹配quiz_type或包含"测试"关键词
                        if quiz_type in elem.text or '测试' in elem.text or '作业' in elem.text:
                            # 排除已完成的测试
                            if '已完成' not in elem.text and '已提交' not in elem.text:
                                self.quiz_container = elem
                                self.logger.info(f"找到测试容器: {elem.text[:30]}")
                                
                                # 查找容器内的"开始做题"按钮
                                self.quiz_element = self.find_start_button(elem)
                                if self.quiz_element:
                                    return True
                except Exception as e:
                    continue
            
            return False
            
        except Exception as e:
            self.logger.error(f"查找测试入口失败: {e}")
            return False
    
    def switch_to_exam_tab(self):
        """切换到作业考试tab"""
        try:
            # 查找"作业考试"tab
            tab_selectors = [
                "//div[contains(text(), '作业考试')]",
                "//span[contains(text(), '作业考试')]",
                "//a[contains(text(), '作业考试')]",
                "//div[contains(text(), '考试')]",
            ]
            
            for selector in tab_selectors:
                try:
                    tabs = self.driver.find_elements(By.XPATH, selector)
                    for tab in tabs:
                        if '作业' in tab.text or '考试' in tab.text:
                            self.logger.info(f"切换到tab: {tab.text}")
                            tab.click()
                            self.smart_wait(2)
                            return True
                except:
                    continue
            
            self.logger.info("未找到作业考试tab，可能已在该页面")
            return True
            
        except Exception as e:
            self.logger.error(f"切换tab失败: {e}")
            return False
    
    def find_start_button(self, container):
        """在测试容器内查找开始按钮"""
        try:
            # 【优化】在容器内查找"开始做题"按钮（不要点击题目标题）
            button_selectors = [
                # 优先查找精确包含"开始做题"的按钮
                ".//button[contains(text(), '开始做题')]",
                ".//div[contains(text(), '开始做题')]",
                ".//a[contains(text(), '开始做题')]",
                ".//span[contains(text(), '开始做题')]",
                # 绿色按钮的class
                ".//div[contains(@class, 'btn') and contains(@class, 'start')]",
                ".//div[contains(@class, 'btn') and contains(@class, 'do')]",
                ".//button[contains(@class, 'start')]",
                # 其他开始相关
                ".//button[contains(text(), '开始')]",
                ".//div[contains(text(), '开始')]",
                ".//span[contains(text(), '开始')]",
                ".//a[contains(text(), '开始')]",
            ]
            
            for selector in button_selectors:
                try:
                    buttons = container.find_elements(By.XPATH, selector)
                    for btn in buttons:
                        btn_text = btn.text.strip()
                        btn_class = btn.get_attribute('class') or ''
                        
                        # 【优化】精确匹配"开始做题"按钮
                        if '开始做题' in btn_text:
                            self.logger.info(f"✅ 找到'开始做题'按钮: {btn_text}")
                            return btn
                        # 其他"开始"按钮
                        elif '开始' in btn_text and ('测试' in btn_text or '考试' in btn_text):
                            self.logger.info(f"✅ 找到开始按钮: {btn_text}")
                            return btn
                        # 根据class匹配
                        elif 'do' in btn_class.lower() or 'start' in btn_class.lower():
                            if btn.is_displayed() and btn.is_enabled():
                                self.logger.info(f"✅ 找到按钮class: {btn_class[:50]}")
                                return btn
                except:
                    continue
            
            # 【修改】如果没找到具体按钮，记录警告但不返回容器
            self.logger.warning("⚠️  未找到'开始做题'按钮，尝试在全页面查找...")
            
            # 尝试在全页面查找
            global_selectors = [
                "//button[contains(text(), '开始做题')]",
                "//div[contains(text(), '开始做题')]",
                "//a[contains(text(), '开始做题')]",
            ]
            
            for selector in global_selectors:
                try:
                    buttons = self.driver.find_elements(By.XPATH, selector)
                    for btn in buttons:
                        if '开始做题' in btn.text and btn.is_displayed():
                            self.logger.info(f"✅ 全页面找到'开始做题'按钮: {btn.text}")
                            return btn
                except:
                    continue
            
            # 如果还是没找到，返回None而不是容器
            self.logger.error("❌ 未找到'开始做题'按钮")
            return None
            
        except Exception as e:
            self.logger.error(f"查找开始按钮失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
    
    def check_quiz_completed(self):
        """检查测试是否已完成"""
        try:
            if not self.quiz_element:
                return False
            
            # 检查是否包含"已完成"、"已提交"等关键词
            element_text = self.quiz_element.text
            completed_keywords = ['已完成', '已提交', '已做', '100%', '满分']
            
            for keyword in completed_keywords:
                if keyword in element_text:
                    self.logger.info(f"检测到测试已完成: {element_text[:30]}")
                    return True
            
            # 检查进度记录
            quiz_id = self.quiz_element.get_attribute('id') or element_text[:20]
            if quiz_id in self.progress.get('completed_quizzes', []):
                self.logger.info(f"进度记录显示该测试已完成: {quiz_id}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"检查测试完成状态失败: {e}")
            return False
    
    def enter_quiz(self):
        """进入测试"""
        try:
            if not self.quiz_element:
                self.logger.error("测试元素不存在")
                return False
            
            self.logger.info("正在进入测试...")
            
            # 滚动到元素可见
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", self.quiz_element)
            self.smart_wait(1)
            
            # 使用ActionChains点击（反检测）
            actions = ActionChains(self.driver)
            actions.move_to_element(self.quiz_element)
            actions.pause(random.uniform(0.5, 1.5))  # 模拟思考
            actions.click()
            actions.perform()
            
            self.logger.info("已点击测试入口")
            self.smart_wait(3)
            
            # 检查是否需要切换窗口/iframe
            self.handle_window_switch()
            
            # 等待答题页面加载
            if self.wait_for_quiz_page():
                return True
            else:
                self.logger.error("答题页面加载超时")
                return False
                
        except Exception as e:
            self.logger.error(f"进入测试失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def handle_window_switch(self):
        """处理窗口/iframe切换"""
        try:
            # 检查是否有新窗口打开
            current_windows = self.driver.window_handles
            if len(current_windows) > 1:
                self.logger.info("检测到新窗口，切换到新窗口")
                self.driver.switch_to.window(current_windows[-1])
                self.smart_wait(2)
            
            # 检查是否有iframe需要切换
            try:
                iframes = self.driver.find_elements(By.TAG_NAME, 'iframe')
                if iframes:
                    self.logger.info(f"检测到 {len(iframes)} 个iframe")
                    # 通常答题页面在第一个iframe中
                    for iframe in iframes:
                        try:
                            self.driver.switch_to.frame(iframe)
                            self.logger.info("已切换到iframe")
                            self.smart_wait(1)
                            break
                        except:
                            self.driver.switch_to.default_content()
                            continue
            except Exception as e:
                self.logger.debug(f"iframe检查: {e}")
                
        except Exception as e:
            self.logger.error(f"窗口切换处理失败: {e}")
    
    def wait_for_quiz_page(self):
        """等待答题页面加载完成"""
        try:
            self.logger.info("等待答题页面加载...")
            
            # 等待题目容器出现的多种选择器
            quiz_page_selectors = [
                "//div[contains(@class, 'topic')]",
                "//div[contains(@class, 'question')]",
                "//div[contains(@class, 'exam')]",
                "//div[contains(@class, 'test')]",
                "//li[contains(@class, 'topic-item')]",
            ]
            
            for selector in quiz_page_selectors:
                try:
                    element = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    if element:
                        self.logger.info(f"✅ 答题页面加载成功，检测到元素: {selector}")
                        return True
                except TimeoutException:
                    continue
            
            # 如果没有找到特定元素，检查URL是否变化
            current_url = self.driver.current_url
            if 'exam' in current_url or 'test' in current_url or 'quiz' in current_url:
                self.logger.info(f"✅ 根据URL判断已进入答题页面: {current_url}")
                return True
            
            self.logger.warning("⚠️  未检测到标准答题页面元素")
            return False
            
        except Exception as e:
            self.logger.error(f"等待答题页面加载失败: {e}")
            return False
    
    def answer_all_questions(self):
        """答题主循环"""
        try:
            self.logger.info("\n" + "="*60)
            self.logger.info("📝 开始答题")
            self.logger.info("="*60)
            
            max_questions = 100  # 防止死循环
            question_count = 0
            
            while question_count < max_questions:
                question_count += 1
                self.logger.info(f"\n--- 题目 {question_count} ---")
                
                # 提取题目信息
                question_data = self.extract_question()
                
                if not question_data:
                    self.logger.warning("⚠️  未能提取题目，尝试查找提交按钮")
                    if self.check_and_submit():
                        self.logger.info("✅ 已提交测试")
                        break
                    else:
                        self.logger.error("❌ 无法继续答题")
                        break
                
                # 调用API获取答案
                answer = self.get_answer_from_api(question_data)
                
                if not answer:
                    self.logger.warning("⚠️  API返回空答案，随机选择")
                    answer = self.random_answer(question_data)
                
                # 选择答案
                if self.select_answer(answer, question_data):
                    self.questions_answered += 1
                    self.logger.info(f"✅ 已答题: {self.questions_answered}")
                else:
                    self.logger.error("❌ 选择答案失败")
                
                # 检查是否有下一题按钮
                if not self.click_next_button():
                    self.logger.info("ℹ️  没有下一题按钮，尝试提交")
                    if self.check_and_submit():
                        self.logger.info("✅ 已提交测试")
                        break
                    else:
                        self.logger.info("ℹ️  答题结束")
                        break
                
                # 随机延时（反检测）
                self.smart_wait(random.uniform(1, 2))
            
            self.logger.info(f"\n✅ 答题完成，共答 {self.questions_answered} 题")
            
        except Exception as e:
            self.logger.error(f"答题过程出错: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def extract_question(self):
        """提取题目和选项"""
        try:
            # 模拟阅读题目时间（反检测）
            self.smart_wait(random.uniform(2, 4))
            
            # 查找题目文本
            question_text = self.find_question_text()
            if not question_text:
                return None
            
            # 查找选项
            options = self.find_options()
            if not options:
                self.logger.warning("⚠️  未找到选项")
                return None
            
            # 判断题型
            question_type = self.detect_question_type()
            
            question_data = {
                'question': question_text,
                'options': options,
                'type': question_type
            }
            
            self.logger.info(f"📝 题目: {question_text[:50]}...")
            self.logger.info(f"📊 选项数量: {len(options)}")
            self.logger.info(f"🏷️  题型: {question_type}")
            
            return question_data
            
        except Exception as e:
            self.logger.error(f"提取题目失败: {e}")
            return None
    
    def find_question_text(self):
        """查找题目文本"""
        try:
            # 【优化】根据实际页面结构调整
            # 题目通常在页面主体区域，包含【单选题】、【多选题】等标识
            question_selectors = [
                # 知到平台专用选择器
                "//div[contains(@class, 'questionlist')]",
                "//div[contains(@class, 'question-item')]",
                "//div[contains(@class, 'Questionlistall')]",
                # 通用选择器
                "//div[contains(@class, 'topic-title')]",
                "//div[contains(@class, 'question-text')]",
                "//div[contains(@class, 'stem')]",
                "//div[contains(@class, 'topic-stem')]",
                "//p[contains(@class, 'question')]",
                "//div[contains(@class, 'exam-question')]",
            ]
            
            for selector in question_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for elem in elements:
                        text = elem.text.strip()
                        # 过滤题目标识前缀
                        if text and len(text) > 5:
                            # 移除题号和题型标识
                            # 例如: "1. 【单选题】 (1分)\n题目内容"
                            import re
                            # 移除题号（数字. 或 数字、）
                            text = re.sub(r'^\d+[.、]\s*', '', text)
                            # 移除题型标识（【单选题】、【多选题】等）
                            text = re.sub(r'【[^】]+】\s*', '', text)
                            # 移除分数标识（(1分)、(2分)等）
                            text = re.sub(r'\(\d+分\)\s*', '', text)
                            
                            text = text.strip()
                            if text and len(text) > 5:
                                return text
                except:
                    continue
            
            self.logger.warning("⚠️  未找到题目文本")
            return None
            
        except Exception as e:
            self.logger.error(f"查找题目文本失败: {e}")
            return None
    
    def find_options(self):
        """查找选项"""
        try:
            options = {}
            
            # 【优化】根据实际页面结构，选项通常是 A. B. C. D. 开头的文本
            # 查找选项的多种选择器
            option_selectors = [
                "//li[contains(@class, 'topic-item')]",  # 知到平台专用
                "//label[contains(@class, 'el-radio')]",
                "//label[contains(@class, 'el-checkbox')]",
                "//div[contains(@class, 'option')]",
            ]
            
            option_elements = []
            for selector in option_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements:
                        option_elements = elements
                        self.logger.info(f"使用选择器找到选项: {selector}, 数量: {len(elements)}")
                        break
                except:
                    continue
            
            # 如果没找到通过class，尝试直接找 A. B. C. D. 开头的所有元素
            if not option_elements:
                self.logger.info("尝试通过文本匹配查找选项...")
                all_text_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'A.') or contains(text(), 'B.') or contains(text(), 'C.') or contains(text(), 'D.')]")
                # 过滤出以 A. B. C. D. 开头的元素
                option_elements = [elem for elem in all_text_elements 
                                 if elem.text.strip() and 
                                 len(elem.text.strip()) > 2 and 
                                 elem.text.strip()[0] in 'ABCDEF' and 
                                 elem.text.strip()[1] in '. 、']
            
            if not option_elements:
                self.logger.warning("⚠️  未找到任何选项元素")
                return None
            
            # 提取选项文本
            option_labels = ['A', 'B', 'C', 'D', 'E', 'F']
            for i, elem in enumerate(option_elements[:6]):  # 最多6个选项
                try:
                    text = elem.text.strip()
                    if not text:
                        continue
                    
                    # 智能识别选项标签
                    detected_label = None
                    for label in option_labels:
                        # 支持多种格式: A. / A、 / A） / A
                        if text.startswith(f'{label}.') or text.startswith(f'{label}、') or text.startswith(f'{label}）') or text.startswith(f'{label} '):
                            detected_label = label
                            # 移除选项前缀
                            for prefix in [f'{label}.', f'{label}、', f'{label}）', f'{label} ']:
                                if text.startswith(prefix):
                                    text = text[len(prefix):].strip()
                                    break
                            break
                    
                    # 如果没检测到标签，使用顺序
                    if not detected_label:
                        detected_label = option_labels[i]
                    
                    if text:
                        options[detected_label] = {
                            'text': text,
                            'element': elem
                        }
                        self.logger.debug(f"选项 {detected_label}: {text[:30]}...")
                except Exception as e:
                    self.logger.debug(f"处理选项 {i} 失败: {e}")
                    continue
            
            if not options:
                self.logger.warning("⚠️  未提取到有效选项")
                return None
            
            return options
            
        except Exception as e:
            self.logger.error(f"查找选项失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
    
    def detect_question_type(self):
        """检测题型"""
        try:
            # 【优化】根据题目标题中的标识判断题型
            try:
                # 查找题目区域的文本
                question_area = self.driver.find_element(By.XPATH, "//body").text
                
                # 优先检查题目标题
                if '【多选题】' in question_area or '（多选）' in question_area:
                    return 'multiple'
                elif '【判断题】' in question_area or '（判断）' in question_area:
                    return 'judge'
                elif '【单选题】' in question_area or '（单选）' in question_area:
                    return 'single'
            except:
                pass
            
            # 检查是否有checkbox（多选题）
            checkboxes = self.driver.find_elements(By.XPATH, "//input[@type='checkbox']")
            if checkboxes:
                return 'multiple'
            
            # 检查是否有radio（单选题）
            radios = self.driver.find_elements(By.XPATH, "//input[@type='radio']")
            if radios:
                return 'single'
            
            # 默认为单选题
            return 'single'
            
        except Exception as e:
            self.logger.error(f"检测题型失败: {e}")
            return 'single'
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def get_answer_from_api(self, question_data):
        """调用API获取答案"""
        try:
            if not self.api_key:
                self.logger.warning("⚠️  未API配置密钥")
                return None
            
            question = question_data['question']
            options = question_data['options']
            question_type = question_data['type']
            
            # 构造选项文本
            options_text = '\n'.join([f"{k}. {v['text']}" for k, v in options.items()])
            
            # 构造Prompt
            user_prompt = f"""请回答以下题目：

题目：{question}

选项：
{options_text}

请直接返回答案字母（单选题返回A/B/C/D，多选题返回AB/ABC等），不需要解释。"""
            
            # 构造请求
            url = f"{self.api_base_url}/v1/chat/completions"
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            data = {
                'model': self.api_model,
                'messages': [
                    {
                        'role': 'system',
                        'content': '你是一个专业的答题助手，只返回答案字母，不要添加任何额外说明。'
                    },
                    {
                        'role': 'user',
                        'content': user_prompt
                    }
                ],
                'temperature': 0.3,
                'max_tokens': 10
            }
            
            self.logger.info(f"🤖 调用API获取答案...")
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            answer_text = result['choices'][0]['message']['content'].strip()
            
            # 提取答案字母
            answer = self.parse_answer(answer_text)
            
            self.logger.info(f"✅ API返回答案: {answer}")
            return answer
            
        except Exception as e:
            self.logger.error(f"API调用失败: {e}")
            return None
    
    def parse_answer(self, answer_text):
        """解析API返回的答案"""
        try:
            # 移除所有空格和特殊字符
            answer_text = answer_text.upper().strip()
            answer_text = ''.join(c for c in answer_text if c in 'ABCDEF')
            
            if not answer_text:
                return None
            
            # 单选题只取第一个字母
            if len(answer_text) == 1:
                return answer_text
            
            # 多选题返回列表
            return list(answer_text)
            
        except Exception as e:
            self.logger.error(f"解析答案失败: {e}")
            return None
    
    def random_answer(self, question_data):
        """随机生成答案（兼底策略）"""
        try:
            options = list(question_data['options'].keys())
            question_type = question_data['type']
            
            if question_type == 'multiple':
                # 多选题随机选2-3个
                num_choices = random.randint(2, min(3, len(options)))
                return random.sample(options, num_choices)
            else:
                # 单选题随机选1个
                return random.choice(options)
                
        except Exception as e:
            self.logger.error(f"随机答案生成失败: {e}")
            return 'A'
    
    def select_answer(self, answer, question_data):
        """选择答案（使用ActionChains）"""
        try:
            options = question_data['options']
            question_type = question_data['type']
            
            # 确保答案是列表格式
            if isinstance(answer, str):
                answer = [answer]
            
            self.logger.info(f"👆 选择答案: {', '.join(answer)}")
            
            # 按顺序点击选项
            for ans in answer:
                if ans not in options:
                    self.logger.warning(f"⚠️  答案 {ans} 不在选项中")
                    continue
                
                option_elem = options[ans]['element']
                
                # 【优化】尝试查找元素内的单选/多选按钮
                clickable_elem = self.find_clickable_element(option_elem)
                
                # 滚动到元素可见
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", clickable_elem)
                self.smart_wait(0.5)
                
                # 使用ActionChains点击（反检测）
                actions = ActionChains(self.driver)
                actions.move_to_element(clickable_elem)
                actions.pause(random.uniform(0.3, 0.8))  # 模拟思考
                actions.click()
                actions.perform()
                
                self.logger.info(f"✅ 已点击选项: {ans}")
                
                # 多选题选项间稍微延时
                if question_type == 'multiple' and len(answer) > 1:
                    self.smart_wait(random.uniform(0.5, 1.0))
            
            # 选完答案后稍微停顿
            self.smart_wait(random.uniform(1, 2))
            return True
            
        except Exception as e:
            self.logger.error(f"选择答案失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def find_clickable_element(self, parent_elem):
        """在选项元素内查找可点击的子元素"""
        try:
            # 【优化】根据实际DOM结构，查找 el-radio__inner / el-checkbox__inner
            clickable_selectors = [
                ".//span[contains(@class, 'el-radio__inner')]",
                ".//span[contains(@class, 'el-checkbox__inner')]",
                ".//input[@type='radio']",
                ".//input[@type='checkbox']",
                ".//label",
            ]
            
            for selector in clickable_selectors:
                try:
                    elem = parent_elem.find_element(By.XPATH, selector)
                    if elem:
                        self.logger.debug(f"找到可点击元素: {selector}")
                        return elem
                except:
                    continue
            
            # 如果没找到子元素，返回父元素
            self.logger.debug("使用父元素作为点击目标")
            return parent_elem
            
        except Exception as e:
            self.logger.error(f"查找可点击元素失败: {e}")
            return parent_elem
    
    def click_next_button(self):
        """点击下一题按钮"""
        try:
            # 【优化】根据实际页面结构
            next_selectors = [
                # 知到平台专用class
                "//span[contains(@class, 'Topicswitchingbtn') and contains(text(), '下一题')]",
                "//div[contains(@class, 'Topicswitchingbtn') and contains(text(), '下一题')]",
                # 通用选择器
                "//button[contains(text(), '下一题')]",
                "//span[contains(text(), '下一题')]",
                "//div[contains(text(), '下一题')]",
                "//a[contains(text(), '下一题')]",
                "//button[contains(@class, 'next')]",
            ]
            
            for selector in next_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for elem in elements:
                        if '下一题' in elem.text or 'next' in elem.get_attribute('class').lower():
                            # 使用ActionChains点击
                            actions = ActionChains(self.driver)
                            actions.move_to_element(elem)
                            actions.pause(random.uniform(0.5, 1.0))
                            actions.click()
                            actions.perform()
                            
                            self.logger.info("✅ 已点击下一题")
                            self.smart_wait(2)
                            return True
                except:
                    continue
            
            self.logger.info("ℹ️  未找到下一题按钮")
            return False
            
        except Exception as e:
            self.logger.error(f"点击下一题失败: {e}")
            return False
    
    def check_and_submit(self):
        """检查并点击提交按钮"""
        try:
            # 【优化】根据实际页面结构
            submit_selectors = [
                # 知到平台专用class
                "//span[contains(@class, 'Submithomeworkbtn')]",
                "//div[contains(@class, 'Submithomeworkbtn')]",
                # 通用选择器
                "//button[contains(text(), '提交')]",
                "//span[contains(text(), '提交')]",
                "//div[contains(text(), '提交')]",
                "//button[contains(text(), '交卷')]",
                "//span[contains(text(), '交卷')]",
                "//span[contains(text(), '提交作业')]",
            ]
            
            for selector in submit_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for elem in elements:
                        if '提交' in elem.text or '交卷' in elem.text:
                            self.logger.info("📝 找到提交按钮")
                            
                            # 提交前稍微等待（反检测）
                            self.smart_wait(random.uniform(2, 4))
                            
                            # 使用ActionChains点击
                            actions = ActionChains(self.driver)
                            actions.move_to_element(elem)
                            actions.pause(random.uniform(1.0, 2.0))
                            actions.click()
                            actions.perform()
                            
                            self.logger.info("✅ 已点击提交")
                            self.smart_wait(3)
                            
                            # 处理确认弹窗
                            self.handle_submit_confirm()
                            
                            return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            self.logger.error(f"提交测试失败: {e}")
            return False
    
    def handle_submit_confirm(self):
        """处理提交确认弹窗"""
        try:
            confirm_selectors = [
                "//button[contains(text(), '确定')]",
                "//span[contains(text(), '确认')]",
                "//button[contains(text(), '确认')]",
            ]
            
            self.smart_wait(1)
            
            for selector in confirm_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            elem.click()
                            self.logger.info("✅ 已确认提交")
                            self.smart_wait(2)
                            return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            self.logger.error(f"处理确认弹窗失败: {e}")
            return False
    
    def run(self):
        """运行纯答题模式"""
        try:
            self.logger.info("\n" + "="*60)
            self.logger.info("📋 任务开始 - 纯答题模式")
            self.logger.info("="*60)
            
            # 登录
            if not self.login():
                self.logger.error("❌ 登录失败，程序退出")
                return
            
            self.logger.info("✅ 登录成功，开始查找测试")
            
            # 查找并进入测试
            if not self.find_and_enter_quiz():
                self.logger.error("❌ 未找到测试或进入测试失败")
                return
            
            self.logger.info("✅ 成功进入答题页面")
            
            # 开始答题循环
            self.answer_all_questions()
            
            self.logger.info("✅ 答题任务完成")
            
        except Exception as e:
            self.logger.error(f"运行过程中出现错误: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        finally:
            self.save_progress()
            self.cleanup()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='知到网页版自动播放器 - 纯答题模式')
    parser.add_argument('--account', type=str, default='account.json', help='账号配置文件')
    parser.add_argument('--headless', action='store_true', help='无头模式运行')
    
    args = parser.parse_args()
    
    player = ZhidaoQuizOnlyPlayer(account_file=args.account, headless=args.headless)
    player.run()

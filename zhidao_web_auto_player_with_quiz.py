#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知到网页版自动播放脚本 - 有题目版本 (v2.0)
支持自动播放、题目弹窗处理、侧边栏导航、新版布局支持
"""

import time
import json
import os
import sys
import random
import logging
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service


class ZhidaoWebAutoPlayerWithQuiz:
    """知到网页版自动播放器 - 有题目版本"""
    
    def __init__(self, account_file='account.json', headless=False):
        """初始化播放器"""
        self.account_file = account_file
        
        # 加载配置
        self.config = self.load_config()
        self.account_config = self.load_account_config()
        self.progress = self.load_progress()
        
        # 设置日志（必须在check_and_cleanup_logs之前）
        self.setup_logging()
        
        # 运行次数计数器（每20次清理一次日志）
        self.check_and_cleanup_logs()
        
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
        # 从account文件名提取账号编号
        account_num = self.account_file.replace('account', '').replace('.json', '')
        if not account_num:
            account_num = '1'
        
        log_file = f'zhidao_account{account_num}_quiz.log'
        
        # 配置日志
        self.logger = logging.getLogger(f'ZhidaoQuiz_{account_num}')
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
    
    def check_and_cleanup_logs(self):
        """检查并清理日志文件"""
        account_num = self.account_file.replace('account', '').replace('.json', '')
        if not account_num:
            account_num = '1'
        
        log_file = f'zhidao_account{account_num}_quiz.log'
        
        # 检查日志文件大小
        if os.path.exists(log_file):
            file_size = os.path.getsize(log_file) / (1024 * 1024)  # MB
            if file_size > 20:
                try:
                    os.remove(log_file)
                    print(f"✅ 日志文件超过20MB，已清理: {log_file}")
                except Exception as e:
                    print(f"清理日志失败: {e}")
    
    def load_config(self):
        """加载全局配置"""
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
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
            return json.load(f)
    
    def load_progress(self):
        """加载进度记录"""
        account_num = self.account_file.replace('account', '').replace('.json', '')
        if not account_num:
            account_num = '1'
        
        progress_file = f'progress_account{account_num}.json'
        
        if os.path.exists(progress_file):
            with open(progress_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            'total_watched': 0,
            'total_quizzes': 0,
            'completed_videos': [],
            'last_run': None
        }
    
    def save_progress(self):
        """保存进度记录"""
        account_num = self.account_file.replace('account', '').replace('.json', '')
        if not account_num:
            account_num = '1'
        
        progress_file = f'progress_account{account_num}.json'
        
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
        chrome_options.add_argument('--window-size=1349,768')  # 设置窗口大小
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        # 禁用自动化提示
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            # 尝试使用webdriver-manager自动管理驱动
            try:
                self.logger.info("尝试使用webdriver-manager自动下载ChromeDriver...")
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                self.logger.info("✅ 使用webdriver-manager初始化成功")
            except Exception as download_error:
                self.logger.warning(f"⚠️  webdriver-manager下载失败: {str(download_error)[:100]}")
                self.logger.info("🔄 尝试使用系统环境中的ChromeDriver...")
                
                try:
                    self.driver = webdriver.Chrome(options=chrome_options)
                    self.logger.info("✅ 使用系统 ChromeDriver 初始化成功")
                except Exception as system_error:
                    self.logger.error(f"❌ 系统ChromeDriver也失败: {system_error}")
                    self.logger.error("\n解决方案：")
                    self.logger.error("1. 检查网络连接，确保可以访问国外网站")
                    self.logger.error("2. 或者手动下载ChromeDriver: https://googlechromelabs.github.io/chrome-for-testing/")
                    self.logger.error("3. 将chromedriver.exe放入系统PATH或当前目录")
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
            self.logger.warning(f"点击登录按钮失败，尝试JavaScript点击: {e}")
            try:
                self.driver.execute_script("arguments[0].click();", login_btn)
                self.logger.info("已通过JavaScript点击登录按钮")
            except Exception as e2:
                self.logger.error(f"JavaScript点击也失败: {e2}")
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
            if (loginButtons.length > 0) {{
                loginButtons[0].click();
                return true;
            }}
        }}
        return false;
        """

        result = self.driver.execute_script(script)
        return result
    
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
            return self.find_course_in_sidebar(course_name)
        else:
            self.logger.info("📜 使用老版主区域查找逻辑")
            return self.find_course_legacy(course_name)
    
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
                    if tabs:
                        shared_tab = tabs[0]
                        self.logger.info(f"✅ 找到'共享课'标签: {tab_selector}")
                        break
                except:
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
                    shared_tab.click()
                except:
                    self.driver.execute_script("arguments[0].click();", shared_tab)
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
                
                # 步骤5：精确匹配课程卡片（根据要求.txt）
                for idx, card in enumerate(unique_cards, 1):
                    try:
                        card_text = card.text or ''
                        
                        # 条件1：标题包含课程名
                        if course_name not in card_text:
                            continue
                        
                        # 排除“重要提醒”区域
                        card_classes = card.get_attribute('class') or ''
                        card_id = card.get_attribute('id') or ''
                        if 'important' in card_classes.lower() or 'reminder' in card_classes.lower() or 'carousel' in card_classes.lower():
                            self.logger.debug(f"⚠️  跳过重要提醒区卡片: {card_id}")
                            continue
                        
                        # 排除书名号和直播课
                        if '《' in card_text or '》' in card_text:
                            self.logger.debug(f"⚠️  排除书名号: {card_text[:40]}")
                            continue
                        if '直播' in card_text or '见面课' in card_text:
                            self.logger.debug(f"⚠️  排除直播课: {card_text[:40]}")
                            continue
                        
                        # 条件2：匹配进度文本（正则：进度\s*:\s*\d+(\.\d+)?%）
                        import re
                        progress_match = re.search(r'进度\s*[:：]\s*(\d+(?:\.\d+)?)%', card_text)
                        if not progress_match:
                            self.logger.debug(f"⚠️  未找到进度信息: {card_text[:60]}")
                            continue
                        
                        progress_value = progress_match.group(1)
                        self.logger.info(f"✅ 找到进度: {progress_value}%")
                        
                        # 条件3：包含教师/机构名称（白名单）
                        teacher_keywords = ['吉林大学', '北京大学', '清华大学', '北京师范大学', '中山大学', '南京大学',
                                           '杨振斌', '李娜', '王芳', '张伟']
                        
                        found_teacher = False
                        for keyword in teacher_keywords:
                            if keyword in card_text:
                                self.logger.info(f"✅ 找到教师/机构: {keyword}")
                                found_teacher = True
                                break
                        
                        if not found_teacher:
                            self.logger.debug(f"⚠️  未找到匹配的教师/机构: {card_text[:60]}")
                            continue
                        
                        # 条件4：可选-检查是否有图片封面
                        has_image = len(card.find_elements(By.TAG_NAME, 'img')) > 0
                        if has_image:
                            self.logger.info("✅ 卡片包含图片封面")
                        
                        # 所有条件匹配，点击该卡片
                        self.logger.info(f"🎯 找到符合条件的课程卡片 #{idx}: {card_text[:80]}")
                        
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
                        
                        # 多策略点击
                        try:
                            link.click()
                            self.logger.info("✅ 普通点击成功")
                        except:
                            try:
                                self.driver.execute_script("arguments[0].click();", link)
                                self.logger.info("✅ JavaScript点击成功")
                            except Exception as e:
                                self.logger.error(f"点击失败: {e}")
                                continue
                        
                        # 等待页面跳转
                        self.smart_wait(5)
                        
                        # 验证是否进入课程详情页
                        new_url = self.driver.current_url
                        if 'course' in new_url.lower() or 'detail' in new_url.lower() or 'study' in new_url.lower():
                            self.logger.info(f"✅ 成功进入课程页: {new_url}")
                            return True
                        else:
                            self.logger.warning(f"⚠️  URL未变化，继续尝试下一个: {new_url}")
                    
                    except Exception as card_error:
                        self.logger.debug(f"处理卡片 #{idx} 时出错: {card_error}")
                        continue
            
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
                                
                                # 【改进4】多策略点击：普通点击 → JavaScript点击
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
                                    except Exception as js_err:
                                        self.logger.warning(f"JavaScript点击也失败: {js_err}")
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
                                                    self.driver.execute_script("arguments[0].click();", inner_link)
                                                    self.logger.info("✅ 内部链接JavaScript点击成功")
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
        watched_videos = []  # 新增：记录已观看视频
        
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
                    with open('debug_sidebar.html', 'w', encoding='utf-8') as f:
                        f.write(debug_html)
                    self.logger.warning("⚠️  未找到任何视频元素，已保存侧边栏HTML到 debug_sidebar.html")
                    self.logger.info("🔍 请检查 debug_sidebar.html 文件，查看实际的HTML结构")
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
                            # 记录已观看视频
                            watched_videos.append({
                                'text': text[:100],
                                'title': self._extract_video_title(text)
                            })
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
                                    # 记录已观看视频
                                    watched_videos.append({
                                        'text': text[:100],
                                        'title': self._extract_video_title(text)
                                    })
                                    continue
                                elif progress_value > 0:
                                    # 有进度但未完成，记录进度
                                    self.logger.debug(f"  ℹ️  进度{progress_value}%: {text[:30]}...")
                        except:
                            pass
                        
                        # 方法3：检查文本中是否包含100%或完成关键词
                        if '100%' in text or '已完成' in text or '已学完' in text:
                            self.logger.debug(f"  → 跳过：文本包含完成标记 ({text[:30]}...)")
                            # 记录已观看视频
                            watched_videos.append({
                                'text': text[:100],
                                'title': self._extract_video_title(text)
                            })
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
                            self.driver.execute_script("arguments[0].click();", first_video['element'])
                            self.logger.info("✅ JavaScript点击成功")
                        except Exception as e:
                            self.logger.error(f"❌ 点击视频失败: {e}")
                    
                    self.smart_wait(3)
                    
                    # 启动播放
                    try:
                        play_result = self.driver.execute_script("""
                            var video = document.querySelector('video');
                            if (video) {
                                var playPromise = video.play();
                                if (playPromise !== undefined) {
                                    playPromise.then(function() {
                                        return 'success';
                                    }).catch(function(error) {
                                        return 'error: ' + error.message;
                                    });
                                }
                                return 'video found and play() called';
                            } else {
                                return 'video not found';
                            }
                        """)
                        self.logger.info(f"✅ JavaScript播放结果: {play_result}")
                    except Exception as e:
                        self.logger.warning(f"⚠️  JavaScript启动播放失败: {e}")
                    
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
                                            closeBtn.click();
                                            closedCount++;
                                            closedInfo.push({
                                                keyword: keyword,
                                                btnSelector: closeBtn.tagName + '.' + (closeBtn.className || 'no-class'),
                                                containerClass: container.className
                                            });
                                            console.log('点击关闭按钮:', keyword, closeBtn.className || closeBtn.tagName);
                                        } catch(e) {
                                            console.error('点击关闭按钮失败:', e);
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
                self.logger.info(f"✅ 已点击关闭 {result['count']} 个弹窗")
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
                    
                    # 【建议3】模拟用户行为：移动鼠标到按钮上再点击
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        ActionChains(self.driver).move_to_element(btn).click().perform()
                        self.logger.info(f"✅ 关闭弹窗(鼠标移动): {selector[:60]}")
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
                            # 普通点击失败，尝试JavaScript点击
                            try:
                                self.driver.execute_script("arguments[0].click();", btn)
                                self.logger.info(f"✅ 关闭弹窗(JS): {selector[:60]}")
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
        
        self.logger.info("✅ 弹窗关闭检查完成")
    
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
        """恢复卡停的视频（点击中央+暂停再播放）"""
        try:
            self.logger.warning("🔧 检测到视频卡停，开始恢复...")
            
            # 策略1：点击视频中央区域（最有效，防止自动暂停）
            try:
                self.logger.info("📍 尝试点击视频中央区域恢复播放...")
                video = self.driver.find_element(By.XPATH, "//video")
                # 点击视频中心
                self.driver.execute_script("""
                    var video = arguments[0];
                    var rect = video.getBoundingClientRect();
                    var centerX = rect.left + rect.width / 2;
                    var centerY = rect.top + rect.height / 2;
                    
                    // 创建点击事件
                    var clickEvent = new MouseEvent('click', {
                        view: window,
                        bubbles: true,
                        cancelable: true,
                        clientX: centerX,
                        clientY: centerY
                    });
                    
                    // 获取中心位置的元素并点击
                    var elem = document.elementFromPoint(centerX, centerY);
                    if (elem) {
                        elem.dispatchEvent(clickEvent);
                        console.log('Clicked video center to resume');
                    }
                """, video)
                self.logger.info("✅ 已点击视频中央")
                self.smart_wait(1)
            except Exception as e:
                self.logger.warning(f"点击视频中央失败: {e}")
            
            # 策略2：暂停再播放刷新缓冲
            try:
                self.driver.execute_script("""
                    var video = document.querySelector('video');
                    if (video) {
                        video.pause();
                        setTimeout(function() {
                            video.play();
                        }, 500);
                    }
                """)
                self.logger.info("✅ 执行了暂停-播放操作")
            except Exception as e:
                self.logger.warning(f"暂停-播放操作失败: {e}")
            
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
        """回答题目（依次尝试A-D，直到正确）"""
        try:
            self.logger.info("📝 开始回答题目...")
            
            # 查找所有选项元素（优先级从高到低）
            option_selectors = [
                "//input[@type='radio']",  # 单选框（最优先）
                "//label[contains(@class, 'el-radio')]",  # Element UI单选框标签
                "//div[contains(@class, 'el-radio')]",  # Element UI单选框容器
                "//span[contains(@class, 'el-radio__label')]",  # Element UI单选框文本
                "//div[contains(@class, 'topic-item')]",
                "//div[contains(@class, 'subject-item')]",
                "//div[contains(@class, 'option')]",
                "//label[contains(@class, 'option')]",
            ]
            
            options = []
            for selector in option_selectors:
                try:
                    found_options = self.driver.find_elements(By.XPATH, selector)
                    if found_options:
                        # 过滤出可见的选项
                        visible_options = [opt for opt in found_options if opt.is_displayed()]
                        if visible_options:
                            options = visible_options
                            self.logger.info(f"🔍 找到 {len(visible_options)} 个选项: {selector}")
                            break  # 找到就停止，使用优先级最高的
                except:
                    continue
            
            if not options:
                self.logger.warning("⚠️  未找到题目选项")
                # 尝试直接关闭弹窗
                self.close_quiz_dialog()
                return False
            
            # 依次尝试每个选项，直到正确
            option_labels = ['A', 'B', 'C', 'D']
            max_attempts = min(len(options), 4)  # 最多尝试4个选项
            
            for attempt in range(max_attempts):
                current_label = option_labels[attempt] if attempt < len(option_labels) else f"选项{attempt+1}"
                try:
                    current_option = options[attempt]
                    
                    self.logger.info(f"🎯 尝试选择 {current_label}...")
                    
                    # 点击选项
                    try:
                        current_option.click()
                        self.smart_wait(1)
                    except:
                        # 如果直接点击失败，尝试用JavaScript点击
                        self.driver.execute_script("arguments[0].click();", current_option)
                        self.smart_wait(1)
                    
                    # 查找并点击确定/提交按钮（如果有）
                    submit_buttons = [
                        "//button[contains(text(), '确定')]",
                        "//button[contains(text(), '提交')]",
                        "//div[contains(text(), '确定') and contains(@class, 'btn')]",
                        "//div[contains(@class, 'submit')]",
                    ]
                    
                    for btn_selector in submit_buttons:
                        try:
                            submit_btn = self.driver.find_element(By.XPATH, btn_selector)
                            if submit_btn.is_displayed():
                                submit_btn.click()
                                self.logger.info("✅ 已点击提交")
                                self.smart_wait(2)
                                break
                        except:
                            continue
                    
                    # 等待反馈（可能需要一点时间）
                    self.smart_wait(1.5)
                    
                    # 检查是否正确
                    if self.check_answer_correct():
                        self.logger.info(f"✅ {current_label} 是正确答案！")
                        
                        # 关闭题目弹窗
                        self.smart_wait(1)
                        self.close_quiz_dialog()
                        
                        self.quizzes_answered_this_session += 1
                        self.progress['total_quizzes'] += 1
                        
                        return True
                    else:
                        self.logger.warning(f"❌ {current_label} 不正确，继续尝试...")
                        # 继续下一个选项
                        continue
                    
                except Exception as e:
                    self.logger.error(f"尝试选项 {current_label} 失败: {e}")
                    continue
            
            # 所有选项都尝试完了还是没正确，直接关闭
            self.logger.warning("⚠️  所有选项都尝试完毕，未找到正确答案")
            self.close_quiz_dialog()
            return False
            
        except Exception as e:
            self.logger.error(f"回答题目失败: {e}")
            # 尝试关闭弹窗
            self.close_quiz_dialog()
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
    
    def close_quiz_dialog(self):
        """关闭题目对话框"""
        try:
            close_selectors = [
                "//button[contains(text(), '关闭')]",  # 关闭按钮
                "//div[contains(@class, 'el-icon-close')]",  # Element UI关闭图标
                "//button[contains(@class, 'el-dialog__close')]",  # Element UI对话框关闭
                "//i[contains(@class, 'el-icon-close')]",  # Element UI close图标
                "//i[contains(@class, 'close')]",
                "//*[@title='关闭']",
                "//button[contains(@class, 'close')]",  # 通用关闭按钮
            ]
            
            for selector in close_selectors:
                try:
                    close_btn = self.driver.find_element(By.XPATH, selector)
                    if close_btn.is_displayed():
                        close_btn.click()
                        self.logger.info("✅ 已关闭题目弹窗")
                        self.smart_wait(1)
                        return True
                except:
                    continue
            
            # 如果找不到关闭按钮，尝试按ESC键
            try:
                from selenium.webdriver.common.keys import Keys
                self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                self.logger.info("✅ 已按ESC键关闭弹窗")
                self.smart_wait(1)
                return True
            except:
                pass
            
            return False
            
        except Exception as e:
            self.logger.debug(f"关闭题目弹窗失败: {e}")
            return False
    
    def wait_for_video_complete(self, max_wait_minutes=60):
        """等待当前视频播放完成（带卡停检测）"""
        self.logger.info("⏰ 开始监控视频播放...")
        
        check_interval = 10  # 每10秒检查一次
        max_wait_time = max_wait_minutes * 60  # 最长等待时间（秒）
        elapsed_time = 0
        
        last_progress_check = 0  # 上次检查的进度
        no_progress_count = 0  # 连续无进展次数
        
        start_time = time.time()
        
        while elapsed_time < max_wait_time:
            # 检查是否有题目弹窗
            if self.check_for_quiz():
                self.answer_quiz()
            
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
            
            self.smart_wait(check_interval)
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
            
            # 登录
            if not self.login():
                self.logger.error("❌ 登录失败，程序退出")
                return
            
            # 查找并进入课程
            if not self.find_course():
                self.logger.error("❌ 查找课程失败，程序退出")
                return
            
            # 进入学习页面
            if not self.enter_study_page():
                self.logger.error("❌ 进入学习页面失败，程序退出")
                return
            
            # 查找未观看的视频
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
                        # 如果普通点击失败，尝试JavaScript点击
                        self.driver.execute_script("arguments[0].click();", first_video['element'])
                        self.logger.info("✅ JavaScript点击成功")
                    except Exception as e:
                        self.logger.error(f"❌ 点击视频失败: {e}")
                
                self.smart_wait(3)  # 等待视频加载
                
                # 使用JavaScript直接启动视频播放（支持后台运行）
                self.logger.info("🎯 使用JavaScript启动视频播放...")
                try:
                    # 方案2：直接操作video元素触发播放
                    play_result = self.driver.execute_script("""
                        // 查找video元素
                        var video = document.querySelector('video');
                        if (video) {
                            // 尝试播放
                            var playPromise = video.play();
                            
                            if (playPromise !== undefined) {
                                playPromise.then(function() {
                                    return 'success';
                                }).catch(function(error) {
                                    return 'error: ' + error.message;
                                });
                            }
                            
                            return 'video found and play() called';
                        } else {
                            return 'video not found';
                        }
                    """)
                    
                    if play_result:
                        self.logger.info(f"✅ JavaScript播放结果: {play_result}")
                        self.smart_wait(2)
                    else:
                        self.logger.warning("⚠️  未找到video元素，可能需要等待")
                        
                except Exception as e:
                    self.logger.warning(f"⚠️  JavaScript启动播放失败: {e}，继续监控")
            
            # 主循环：观看视频并回答题目
            self.logger.info("\n" + "="*60)
            self.logger.info("🎬 开始自动播放（视频会自动连续播放）")
            self.logger.info("="*60)
            
            # 用于定时检查重复播放
            check_counter = 0
            check_interval = 6  # 每6次循环（约30秒）检查一次
            
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
        """清理资源"""
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
        
        # 关闭浏览器
        if hasattr(self, 'driver'):
            try:
                self.driver.quit()
                self.logger.info("✅ 浏览器已关闭")
            except:
                pass


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

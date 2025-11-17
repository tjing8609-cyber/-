#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知到网页版自动播放脚本 - 有题目版本 (v1.0)
支持自动播放、题目弹窗处理、侧边栏导航
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
        self.logger.info("知到网页版自动播放器 - 有题目版本 v1.0")
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
        chrome_options.add_argument('--window-size=1920,1080')
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
                            # 验证完成后继续检查登录状态
                            continue
                        
                        # 检查登录是否成功
                        if self.check_login_success():
                            self.logger.info("登录成功！")
                            return True
                        
                        # 检查是否还在登录页面
                        current_url = self.driver.current_url
                        if "login" not in current_url.lower():
                            self.logger.info("已离开登录页面，检查最终状态...")
                            self.smart_wait(2)
                            if self.check_login_success():
                                self.logger.info("登录成功！")
                                return True
                    
                    self.logger.warning(f"等待{max_wait}秒后登录状态仍未确认")
                    # 最后再检查一次
                    if self.check_login_success():
                        self.logger.info("最终检查：登录成功！")
                        return True
                    else:
                        self.logger.warning("最终检查：登录状态不确定")
                        return False
                else:
                    self.logger.warning("登录失败，尝试继续操作")
                    return False
            else:
                self.logger.info("当前已登录或无需登录")
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
            
            return True
            
        except Exception as e:
            self.logger.error(f"进入学习页面失败: {e}")
            return False
    
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
            
            # 主循环：观看视频并回答题目
            self.logger.info("\n" + "="*60)
            self.logger.info("🎬 开始自动播放（视频会自动连续播放）")
            self.logger.info("="*60)
            
            # 由于是自动连续播放，这里主要是监控题目弹窗
            while True:
                self.smart_wait(5)
                
                # 检查题目弹窗
                if self.check_for_quiz():
                    self.answer_quiz()
                
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

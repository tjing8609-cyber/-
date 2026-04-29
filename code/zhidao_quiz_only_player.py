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
from datetime import datetime
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.edge.options import Options as EdgeOptions
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from auth_actions import try_login_methods as auth_try_login_methods
from auth_flow import is_login_required, is_login_success, mask_username
from browser_session import create_browser_session, resolve_local_driver_paths
from deepseek_agent import create_deepseek_components, verify_deepseek_client
from page_detection import (
    is_captcha_present,
    wait_for_captcha_completion as detect_wait_for_captcha_completion,
)
from quiz_answering import (
    allowed_option_labels,
    classify_api_error,
    parse_answer_letters,
)
from quiz_page_actions import (
    click_next_button as action_click_next_button,
    find_clickable_option_element,
    select_answer_options,
)
from quiz_navigation import (
    enter_quiz_page,
    find_quiz_entrance as navigation_find_quiz_entrance,
    handle_window_switch as navigation_handle_window_switch,
    scroll_to_load_all_quizzes as navigation_scroll_to_load_all_quizzes,
    switch_to_exam_tab as navigation_switch_to_exam_tab,
    wait_for_quiz_page as navigation_wait_for_quiz_page,
)
from quiz_page_reader import clean_question_text, detect_question_type_from_text, parse_option_text
from quiz_test_flow import (
    confirm_submit as test_confirm_submit,
    find_start_button as test_find_start_button,
    is_answer_card_ready_for_submit,
    is_last_question as test_is_last_question,
    is_quiz_completed as test_is_quiz_completed,
    log_quiz_status_change,
    submit_quiz,
)


class ZhidaoQuizOnlyPlayer:
    """知到网页版自动播放器 - 纯答题模式"""
    
    def __init__(self, account_file='account.json', headless=False):
        """初始化播放器"""
        self.account_file = account_file
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # 加载配置
        self.config = self.load_config()
        self.account_config = self.load_account_config()
        
        # 【重要】先设置日志，因为后续方法会使用logger
        self.setup_logging()
        
        # 加载进度
        self.progress = self.load_progress()
        
        # 【新增】加载环境变量
        load_dotenv()
        
        self.api_client, self.answering_service, self.deepseek_config = create_deepseek_components(
            self.account_config,
            logger=self.logger,
        )
        self.api_key = self.deepseek_config.api_key
        self.api_base_url = self.deepseek_config.base_url
        self.api_model = self.deepseek_config.model

        if self.api_client:
            self.logger.info("✅ DeepSeek API配置加载成功")
            self.logger.info(f"🔑 API Key来源: {self.deepseek_config.source}")
            self.logger.info(f"📡 API Base URL: {self.api_base_url}")
            self.logger.info(f"🤖 API Model: {self.api_model}")
        else:
            self.logger.warning("⚠️  未配置API密钥（账号配置和环境变量均未找到），答题功能将受限")
        
        verify_api_on_start = self.account_config.get('verify_api_on_start', True)
        if self.api_key and verify_api_on_start:
            if not self.verify_api_connection():
                self.logger.error("❌ API连接验证失败，程序退出")
                self.logger.error("请检查以下配置：")
                self.logger.error(f"  - API密钥是否正确")
                self.logger.error(f"  - API Base URL: {self.api_base_url}")
                self.logger.error(f"  - 网络连接是否正常")
                sys.exit(1)
        elif self.api_key:
            self.logger.info("ℹ️ 已跳过启动API连通性校验（verify_api_on_start=false）")
        
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
        
        # 【修复】确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        # 配置日志
        self.logger = logging.getLogger(f'ZhidaoQuizOnly_{account_num}')
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
    
    def _resolve_local_driver_paths(self):
        return resolve_local_driver_paths(self.project_root)

    def setup_driver(self, headless=False):
        """设置Chrome浏览器驱动"""
        session = create_browser_session(
            self.project_root,
            headless=headless,
            logger=self.logger,
            window_size="1349,768",
        )
        self.driver = session.driver
        self.wait = session.wait
    
    def smart_wait(self, seconds):
        """智能等待（随机波动）"""
        actual_wait = seconds + random.uniform(-0.5, 0.5)
        time.sleep(max(0.5, actual_wait))
    
    def handle_after_submit(self):
        """处理提交后的页面：关闭结果页面，返回题目列表，刷新"""
        try:
            self.logger.info("🔄 处理提交后的页面...")
            
            # 等待页面加载完成
            self.smart_wait(3)
            
            # 检查是否有多个窗口/标签页
            all_windows = self.driver.window_handles
            self.logger.info(f"📊 当前窗口数量: {len(all_windows)}")
            
            if len(all_windows) > 1:
                # 关闭当前窗口（提交结果页）
                current_window = self.driver.current_window_handle
                self.logger.info("📛 关闭提交结果页面...")
                self.driver.close()
                
                # 切换到主窗口
                remaining_windows = [w for w in all_windows if w != current_window]
                if remaining_windows:
                    self.driver.switch_to.window(remaining_windows[0])
                    self.logger.info("✅ 已切换到主窗口")
            else:
                # 只有一个窗口，检查URL是否为提交结果页
                current_url = self.driver.current_url
                self.logger.info(f"🔗 当前URL: {current_url}")
                
                # 如果是提交结果页，返回上一页或点击返回按钮
                if 'doHomeWork' in current_url or 'backUrl' in current_url:
                    self.logger.info("🔙 检测到提交结果页，尝试返回...")
                    
                    # 尝试点击返回按钮
                    return_button_found = False
                    return_selectors = [
                        "//span[contains(text(), '返回')]",
                        "//button[contains(text(), '返回')]",
                        "//a[contains(text(), '返回')]",
                        "//div[contains(@class, '返回')]",
                    ]
                    
                    for selector in return_selectors:
                        try:
                            buttons = self.driver.find_elements(By.XPATH, selector)
                            if buttons:
                                buttons[0].click()
                                self.logger.info("✅ 已点击返回按钮")
                                return_button_found = True
                                break
                        except:
                            continue
                    
                    # 如果没找到返回按钮，使用浏览器后退
                    if not return_button_found:
                        self.logger.info("🔙 使用浏览器后退")
                        self.driver.back()
            
            # 等待页面加载
            self.smart_wait(3)
            
            # 刷新页面获取最新状态
            self.logger.info("🔄 刷新页面获取最新题目状态...")
            self.driver.refresh()
            self.smart_wait(3)
            
            self.logger.info("✅ 已返回题目列表并刷新")
            
            # 检查题目状态变化
            self.check_quiz_status_change()
            
        except Exception as e:
            self.logger.error(f"处理提交后页面失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def check_quiz_status_change(self):
        """检查题目状态变化"""
        try:
            log_quiz_status_change(self.driver, logger=self.logger)
        except Exception as e:
            self.logger.error(f"检查题目状态失败: {e}")
    
    def is_last_question(self):
        """双重判断是否为最后一题"""
        try:
            return test_is_last_question(self.driver, logger=self.logger, wait_func=self.smart_wait)
        except Exception as e:
            self.logger.error(f"检查是否最后一题失败: {e}")
            return False
    
    def check_answer_card(self):
        """检查右侧答题卡，判断是否除了最后一题外其余都已答"""
        try:
            return is_answer_card_ready_for_submit(self.driver, logger=self.logger, wait_func=self.smart_wait)
        except Exception as e:
            self.logger.error(f"检查答题卡失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def handle_api_error(self, error, context="API调用"):
        """处理DeepSeek API错误，根据官方文档提供详细提示"""
        error_str = str(error)
        
        self.logger.error(f"❌ {context}失败: {error}")
        self.logger.error(f"🚫 错误分类: {classify_api_error(error)}")
        
        # 检测并处理常见错误
        if '400' in error_str:
            self.logger.error("🚫 错误类型: 400 - 格式错误")
            self.logger.error("💡 原因: 请求体格式错误")
            self.logger.error("🔧 解决方法: 请检查请求参数是否符合API规范")
        elif '401' in error_str:
            self.logger.error("🚫 错误类型: 401 - 认证失败")
            self.logger.error("💡 原因: API Key 错误，认证失败")
            self.logger.error("🔧 解决方法:")
            self.logger.error("   1. 检查环境变量 DEEPSEEK_API_KEY（优先）或 ANTHROPIC_AUTH_TOKEN（兼容）是否正确")
            self.logger.error("   2. 确认API Key来自 https://platform.deepseek.com/api_keys")
            self.logger.error("   3. 检查API Key是否有多余空格或换行")
        elif '402' in error_str:
            self.logger.error("🚫 错误类型: 402 - 余额不足")
            self.logger.error("💡 原因: 账号余额不足")
            self.logger.error("🔧 解决方法:")
            self.logger.error("   1. 前往 https://platform.deepseek.com/usage 查看余额")
            self.logger.error("   2. 前往 https://platform.deepseek.com/top_up 进行充值")
        elif '422' in error_str:
            self.logger.error("🚫 错误类型: 422 - 参数错误")
            self.logger.error("💡 原因: 请求体参数错误")
            self.logger.error("🔧 解决方法:")
            self.logger.error("   1. 检查model参数是否为 'deepseek-chat' 或 'deepseek-reasoner'")
            self.logger.error("   2. 检查max_tokens、temperature等参数是否在有效范围内")
        elif '429' in error_str:
            self.logger.error("🚫 错误类型: 429 - 请求速率达到上限")
            self.logger.error("💡 原因: 请求速率（TPM 或 RPM）达到上限")
            self.logger.error("🔧 解决方法:")
            self.logger.error("   1. 稍后重试，等待几秒再发起请求")
            self.logger.error("   2. 调整答题间隔时间，降低请求频率")
            self.logger.error("   3. 检查是否有多个程序同时使用同一API Key")
        elif '500' in error_str:
            self.logger.error("🚫 错误类型: 500 - 服务器故障")
            self.logger.error("💡 原因: 服务器内部故障")
            self.logger.error("🔧 解决方法:")
            self.logger.error("   1. 稍后重试")
            self.logger.error("   2. 若问题持续存在，请联系DeepSeek官方支持")
        elif '503' in error_str:
            self.logger.error("🚫 错误类型: 503 - 服务器繁忙")
            self.logger.error("💡 原因: 服务器负载过高")
            self.logger.error("🔧 解决方法:")
            self.logger.error("   1. 稍后重试您的请求")
            self.logger.error("   2. 建议等待30-60秒后再次尝试")
        else:
            # 其他错误，显示详细堆栈
            self.logger.error("🚫 未知错误类型")
            self.logger.error("💡 可能原因:")
            self.logger.error("   1. 网络连接问题")
            self.logger.error("   2. API地址错误")
            self.logger.error("   3. OpenAI SDK版本问题")
            import traceback
            self.logger.error(f"📑 详细堆栈:\n{traceback.format_exc()}")
        
        # 通用检查建议
        self.logger.error("\n🔍 通用检查步骤:")
        self.logger.error(f"   1. API Base URL: {self.api_base_url}")
        self.logger.error(f"   2. API Model: {self.api_model}")
        self.logger.error("   3. 检查网络连接是否正常")
        self.logger.error("   4. 确认已安装 openai 库: pip install openai")
    
    def login(self):
        """登录知到网站"""
        username = self.account_config.get('username')
        password = self.account_config.get('password')
        
        self.logger.info(f"正在登录，账号: {mask_username(username)}")

        try:
            # 打开登录页面
            self.driver.get("https://onlineweb.zhihuishu.com/onlinestuh5")
            self.smart_wait(5)

            # 判断是否需要登录
            need_login = is_login_required(self.driver)

            if need_login:
                self.logger.info("检测到需要登录")
                if not auth_try_login_methods(
                    self.driver,
                    self.wait,
                    username,
                    password,
                    logger=self.logger,
                    wait_func=self.smart_wait,
                ):
                    self.logger.warning("⚠️  自动登录动作未完成，继续等待登录状态")
                
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
            return is_captcha_present(self.driver)
        except Exception as e:
            self.logger.error(f"检查人机验证时出错: {e}")
            return False
    
    def check_login_success(self):
        """检查是否登录成功"""
        try:
            return is_login_success(self.driver)
        except Exception as e:
            self.logger.error(f"检查登录状态时出错: {e}")
            return False
    
    def wait_for_captcha_completion(self, timeout=60):
        """等待用户完成人机验证"""
        return detect_wait_for_captcha_completion(
            self.check_captcha,
            self.check_login_success,
            logger=self.logger,
            timeout=timeout,
        )
    
    def verify_api_connection(self):
        """验证DeepSeek API连接"""
        self.logger.info("\n" + "="*60)
        self.logger.info("🔍 验证DeepSeek API连接...")
        self.logger.info("="*60)
        self.logger.info(f"📡 API Base URL: {self.api_base_url}")
        self.logger.info(f"🤖 使用模型: {self.api_model}")
        validation = verify_deepseek_client(
            self.api_client,
            self.deepseek_config,
            logger=self.logger,
        )
        if not validation.ok:
            self.logger.error(f"❌ DeepSeek启动校验失败: {validation.message}")
        self.logger.info("="*60 + "\n")
        return validation.ok
    
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
        """查找测试入口【优化】添加滚动功能"""
        try:
            entrance = navigation_find_quiz_entrance(
                self.driver,
                quiz_type,
                self.find_start_button,
                logger=self.logger,
                wait_func=self.smart_wait,
            )
            self.quiz_container = entrance.container
            self.quiz_element = entrance.start_button
            return entrance.found
        except Exception as e:
            self.logger.error(f"查找测试入口失败: {e}")
            return False
    
    def switch_to_exam_tab(self):
        """切换到作业考试tab"""
        try:
            return navigation_switch_to_exam_tab(self.driver, logger=self.logger, wait_func=self.smart_wait)
        except Exception as e:
            self.logger.error(f"切换tab失败: {e}")
            return False
    
    def scroll_to_load_all_quizzes(self):
        """滚动页面以加载所有测试项目"""
        try:
            return navigation_scroll_to_load_all_quizzes(self.driver, logger=self.logger, wait_func=self.smart_wait)
        except Exception as e:
            self.logger.warning(f"⚠️  滚动页面失败: {e}，继续查找...")
    
    def find_start_button(self, container):
        """在测试容器内查找开始按钮"""
        try:
            return test_find_start_button(self.driver, container, logger=self.logger)
        except Exception as e:
            self.logger.error(f"查找开始按钮失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
    
    def check_quiz_completed(self):
        """检查测试是否已完成"""
        try:
            return test_is_quiz_completed(self.quiz_element, progress=self.progress, logger=self.logger)
        except Exception as e:
            self.logger.error(f"检查测试完成状态失败: {e}")
            return False
    
    def enter_quiz(self):
        """进入测试"""
        try:
            return enter_quiz_page(
                self.driver,
                self.quiz_element,
                logger=self.logger,
                wait_func=self.smart_wait,
            )
        except Exception as e:
            self.logger.error(f"进入测试失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def handle_window_switch(self):
        """处理窗口/iframe切换"""
        navigation_handle_window_switch(self.driver, logger=self.logger, wait_func=self.smart_wait)
    
    def wait_for_quiz_page(self):
        """等待答题页面加载完成"""
        try:
            return navigation_wait_for_quiz_page(self.driver, logger=self.logger)
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
                
                # 【修改】如果API返回空答案，退出程序而不是随机选择
                if not answer:
                    self.logger.error("❌ API返回空答案，纯答题模式要求准确答题，程序退出")
                    self.logger.error("⚠️  请检查:")
                    self.logger.error("   1. API密钥是否正确")
                    self.logger.error("   2. API连接是否正常")
                    self.logger.error("   3. 题目是否提取完整")
                    self.logger.error("   4. 模型是否支持中文问答")
                    return  # 直接退出答题循环，结束程序
                
                # 选择答案
                if self.select_answer(answer, question_data):
                    self.questions_answered += 1
                    self.logger.info(f"✅ 已答题: {self.questions_answered}")
                else:
                    self.logger.error("❌ 选择答案失败")
                
                # 【优化】检查是否有下一题按钮
                has_next = self.click_next_button()
                
                if not has_next:
                    # 没有下一题，双重检查是否为最后一题
                    self.logger.info("🔍 检测到下一题按钮不可用，进行双重检查...")
                    if self.is_last_question():
                        # 确认是最后一题，尝试提交
                        self.logger.info("🏁 双重确认是最后一题，尝试提交...")
                        if self.check_and_submit():
                            self.logger.info("✅ 已成功提交测试")
                            # 【新增】处理提交后的页面
                            self.handle_after_submit()
                            break
                        else:
                            self.logger.warning("⚠️  提交失败，答题结束")
                            break
                    else:
                        self.logger.warning("⚠️  双重检查未通过，不确认是否最后一题，结束答题")
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
                            text = clean_question_text(text)
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
                    
                    detected_label, text = parse_option_text(text, option_labels[i])
                    
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
                
                detected = detect_question_type_from_text(question_area, default=None)
                if detected:
                    return detected
            except:
                pass
            
            # 检查是否有checkbox（多选题）
            checkboxes = self.driver.find_elements(By.XPATH, "//input[@type='checkbox']")
            if checkboxes:
                return detect_question_type_from_text("", has_checkbox=True)
            
            # 检查是否有radio（单选题）
            radios = self.driver.find_elements(By.XPATH, "//input[@type='radio']")
            if radios:
                return detect_question_type_from_text("", has_radio=True)
            
            # 默认为单选题
            return 'single'
            
        except Exception as e:
            self.logger.error(f"检测题型失败: {e}")
            return 'single'
    
    def get_answer_from_api(self, question_data):
        """调用API获取答案"""
        try:
            if not self.answering_service:
                self.logger.warning("⚠️  未配置API客户端")
                return None

            result = self.answering_service.answer(question_data)
            return result.value if result.valid else None
            
        except Exception as e:
            self.handle_api_error(e, "API答题调用")
            return None
    
    def parse_answer(self, answer_text):
        """解析API返回的答案"""
        try:
            result = parse_answer_letters(answer_text, list("ABCDEF"), "multiple")
            return result.value if result.valid else None
            
        except Exception as e:
            self.logger.error(f"解析答案失败: {e}")
            return None
    
    def random_answer(self, question_data):
        """保留兼容接口：无法可靠判断时不再随机作答。"""
        try:
            labels = allowed_option_labels(question_data)
            self.logger.warning(f"⚠️  无法可靠判断答案，跳过随机作答；可选项: {', '.join(labels)}")
            return None
                
        except Exception as e:
            self.logger.error(f"随机答案生成失败: {e}")
            return None
    
    def select_answer(self, answer, question_data):
        """选择答案（使用ActionChains）"""
        try:
            return select_answer_options(
                self.driver,
                answer,
                question_data,
                logger=self.logger,
                wait_func=self.smart_wait,
            )
        except Exception as e:
            self.logger.error(f"选择答案失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def find_clickable_element(self, parent_elem):
        """在选项元素内查找可点击的子元素"""
        try:
            return find_clickable_option_element(parent_elem, logger=self.logger)
        except Exception as e:
            self.logger.error(f"查找可点击元素失败: {e}")
            return parent_elem
    
    def click_next_button(self):
        """点击下一题按钮，返回是否有下一题"""
        try:
            return action_click_next_button(self.driver, logger=self.logger, wait_func=self.smart_wait)
        except Exception as e:
            self.logger.error(f"点击下一题失败: {e}")
            return False
    
    def check_and_submit(self):
        """检查并点击提交按钮"""
        try:
            return submit_quiz(self.driver, logger=self.logger, wait_func=self.smart_wait)
        except Exception as e:
            self.logger.error(f"提交测试失败: {e}")
            return False
    
    def handle_submit_confirm(self):
        """处理提交确认弹窗"""
        try:
            return test_confirm_submit(self.driver, logger=self.logger, wait_func=self.smart_wait)
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
            
            self.logger.info("✅ 登录成功，开始循环查找测试")
            
            # 【新增】循环查找和答题，直到所有题目都完成
            max_rounds = 100  # 防止死循环，最多100轮
            round_count = 0
            
            while round_count < max_rounds:
                round_count += 1
                self.logger.info(f"\n{'='*60}")
                self.logger.info(f"🔄 第 {round_count} 轮查找测试")
                self.logger.info("="*60)
                
                # 查找并进入测试
                if not self.find_and_enter_quiz():
                    self.logger.info("✅ 所有测试已完成，程序结束")
                    break
                
                self.logger.info("✅ 成功进入答题页面")
                
                # 开始答题循环
                self.answer_all_questions()
                
                self.logger.info(f"✅ 第 {round_count} 轮答题完成")
                
                # 等待一下再进入下一轮
                self.smart_wait(2)
            
            if round_count >= max_rounds:
                self.logger.warning("⚠️  已达到最大轮次限制，程序退出")
            else:
                self.logger.info("✅ 所有答题任务完成")
            
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

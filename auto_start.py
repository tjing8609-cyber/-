#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Copyright (c) 2025 景潼
Zhidao Auto is licensed under Mulan PSL v2.

知到自动播放器 - 图形化启动器 v1.0
支持无代码基础用户通过图形界面操作
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import json
import os
import sys
import threading
import subprocess
import queue
from pathlib import Path

# 【修复】Windows下设置UTF-8编码，避免乱码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


class ZhidaoGUILauncher:
    """知到自动播放器图形化启动器"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("知到自动播放器 - 图形化启动器 v1.0")
        self.root.geometry("900x900")
        
        # 项目路径
        self.project_root = os.path.dirname(os.path.abspath(__file__))
        self.launch_dir = os.path.join(self.project_root, '启动')
        self.code_dir = os.path.join(self.project_root, 'code')
        
        # 当前配置文件
        self.current_account_file = os.path.join(self.launch_dir, 'account.json')
        
        # 运行状态
        self.is_running = False
        self.process = None
        self.log_queue = queue.Queue()
        
        # 创建界面
        self.create_widgets()
        
        # 加载配置
        self.load_config()
        
        # 启动日志监听
        self.update_log()
    
    def create_widgets(self):
        """创建界面组件"""
        
        # ==================== 顶部标题 ====================
        title_frame = tk.Frame(self.root, bg="#34495E", height=50)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        tk.Label(
            title_frame,
            text="🎓 知到自动播放器 - 图形化启动器",
            font=("微软雅黑", 16, "bold"),
            bg="#34495E",
            fg="white"
        ).pack(pady=12)
        
        # ==================== 主滚动区域 ====================
        main_canvas = tk.Canvas(self.root)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=main_canvas.yview)
        scrollable_frame = ttk.Frame(main_canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
        )
        
        main_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=scrollbar.set)
        
        main_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 主容器
        container = tk.Frame(scrollable_frame, padx=15, pady=15)
        container.pack(fill=tk.BOTH, expand=True)
        
        # ==================== 配置文件选择 ====================
        file_frame = tk.LabelFrame(
            container,
            text="📁 配置文件",
            font=("微软雅黑", 10, "bold"),
            padx=10,
            pady=8
        )
        file_frame.pack(fill=tk.X, pady=(0, 10))
        
        file_row = tk.Frame(file_frame)
        file_row.pack(fill=tk.X)
        
        tk.Label(file_row, text="当前配置:", font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=(0, 5))
        
        self.file_label = tk.Label(
            file_row,
            text="account.json",
            font=("微软雅黑", 9),
            fg="blue",
            cursor="hand2"
        )
        self.file_label.pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Button(
            file_row,
            text="📂 选择其他配置",
            command=self.select_account_file,
            font=("微软雅黑", 8),
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            file_row,
            text="➕ 新建配置",
            command=self.create_new_config,
            font=("微软雅黑", 8),
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=2)
        
        # ==================== 账号配置 ====================
        account_frame = tk.LabelFrame(
            container,
            text="📝 账号配置",
            font=("微软雅黑", 10, "bold"),
            padx=10,
            pady=8
        )
        account_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 用户名
        row1 = tk.Frame(account_frame)
        row1.pack(fill=tk.X, pady=3)
        tk.Label(row1, text="用户名:", font=("微软雅黑", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.username_var = tk.StringVar()
        tk.Entry(row1, textvariable=self.username_var, font=("微软雅黑", 9), width=50).pack(side=tk.LEFT, padx=5)
        
        # 密码
        row2 = tk.Frame(account_frame)
        row2.pack(fill=tk.X, pady=3)
        tk.Label(row2, text="密码:", font=("微软雅黑", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.password_var = tk.StringVar()
        tk.Entry(row2, textvariable=self.password_var, show="*", font=("微软雅黑", 9), width=50).pack(side=tk.LEFT, padx=5)
        
        # ==================== 运行模式 ====================
        mode_frame = tk.LabelFrame(
            container,
            text="🎯 运行模式",
            font=("微软雅黑", 10, "bold"),
            padx=10,
            pady=8
        )
        mode_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.mode_var = tk.StringVar(value="video")
        
        mode_row = tk.Frame(mode_frame)
        mode_row.pack(fill=tk.X)
        
        tk.Radiobutton(
            mode_row,
            text="📹 视频播放模式",
            variable=self.mode_var,
            value="video",
            font=("微软雅黑", 9),
            command=self.on_mode_change
        ).pack(side=tk.LEFT, padx=10)
        
        tk.Radiobutton(
            mode_row,
            text="📝 纯答题模式",
            variable=self.mode_var,
            value="quiz_only",
            font=("微软雅黑", 9),
            command=self.on_mode_change
        ).pack(side=tk.LEFT, padx=10)
        
        # ==================== 课程配置 ====================
        course_frame = tk.LabelFrame(
            container,
            text="📚 课程配置",
            font=("微软雅黑", 10, "bold"),
            padx=10,
            pady=8
        )
        course_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 课程名称
        row3 = tk.Frame(course_frame)
        row3.pack(fill=tk.X, pady=3)
        tk.Label(row3, text="课程名称:", font=("微软雅黑", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.course_name_var = tk.StringVar()
        tk.Entry(row3, textvariable=self.course_name_var, font=("微软雅黑", 9), width=50).pack(side=tk.LEFT, padx=5)
        
        # 【新增】课程URL（可选）
        row3_url = tk.Frame(course_frame)
        row3_url.pack(fill=tk.X, pady=3)
        tk.Label(row3_url, text="课程URL:", font=("微软雅黑", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.course_url_var = tk.StringVar()
        tk.Entry(row3_url, textvariable=self.course_url_var, font=("微软雅黑", 9), width=50).pack(side=tk.LEFT, padx=5)
        tk.Label(row3_url, text="(可选，设置后将跳过课程查找)", font=("微软雅黑", 8), fg="gray").pack(side=tk.LEFT)
        
        # ==================== 视频模式配置 ====================
        self.video_frame = tk.LabelFrame(
            container,
            text="📹 视频模式配置",
            font=("微软雅黑", 10, "bold"),
            padx=10,
            pady=8
        )
        self.video_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 课程类型
        row4 = tk.Frame(self.video_frame)
        row4.pack(fill=tk.X, pady=3)
        tk.Label(row4, text="课程类型:", font=("微软雅黑", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.course_type_var = tk.IntVar(value=1)
        tk.Radiobutton(row4, text="1-无题目", variable=self.course_type_var, value=1, font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(row4, text="2-有题目(自动关闭)", variable=self.course_type_var, value=2, font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=5)
        
        # 侧边栏布局
        row5 = tk.Frame(self.video_frame)
        row5.pack(fill=tk.X, pady=3)
        tk.Label(row5, text="侧边栏布局:", font=("微软雅黑", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.sidebar_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            row5,
            text="启用侧边栏布局检测(适用于新版界面)",
            variable=self.sidebar_var,
            font=("微软雅黑", 9)
        ).pack(side=tk.LEFT, padx=5)
        
        # 观看时长
        row6 = tk.Frame(self.video_frame)
        row6.pack(fill=tk.X, pady=3)
        tk.Label(row6, text="观看时长(分钟):", font=("微软雅黑", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.max_watch_minutes_var = tk.IntVar(value=0)
        tk.Spinbox(row6, from_=0, to=999, textvariable=self.max_watch_minutes_var, font=("微软雅黑", 9), width=10).pack(side=tk.LEFT, padx=5)
        tk.Label(row6, text="(0=播放全部)", font=("微软雅黑", 8), fg="gray").pack(side=tk.LEFT)
        
        # ==================== 答题模式配置 ====================
        self.quiz_frame = tk.LabelFrame(
            container,
            text="📝 答题模式配置",
            font=("微软雅黑", 10, "bold"),
            padx=10,
            pady=8
        )
        self.quiz_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 测试类型
        row7 = tk.Frame(self.quiz_frame)
        row7.pack(fill=tk.X, pady=3)
        tk.Label(row7, text="测试类型:", font=("微软雅黑", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.quiz_type_var = tk.StringVar(value="课程测试")
        ttk.Combobox(
            row7,
            textvariable=self.quiz_type_var,
            values=["课程测试", "章节测试", "单元测试", "期末考试"],
            font=("微软雅黑", 9),
            width=20,
            state="readonly"
        ).pack(side=tk.LEFT, padx=5)
        
        # DeepSeek API
        row8 = tk.Frame(self.quiz_frame)
        row8.pack(fill=tk.X, pady=3)
        tk.Label(row8, text="DeepSeek API:", font=("微软雅黑", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.api_key_var = tk.StringVar()
        tk.Entry(row8, textvariable=self.api_key_var, show="*", font=("微软雅黑", 9), width=40).pack(side=tk.LEFT, padx=5)
        # 【新增】读取系统配置按钮
        tk.Button(
            row8,
            text="🔍 读取系统配置",
            command=self.load_system_env_config,
            font=("微软雅黑", 8),
            bg="#F39C12",
            fg="white",
            cursor="hand2",
            width=12
        ).pack(side=tk.LEFT, padx=5)
        
        # API Base URL
        row9 = tk.Frame(self.quiz_frame)
        row9.pack(fill=tk.X, pady=3)
        tk.Label(row9, text="API Base URL:", font=("微软雅黑", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.api_base_url_var = tk.StringVar()
        tk.Entry(row9, textvariable=self.api_base_url_var, font=("微软雅黑", 9), width=50).pack(side=tk.LEFT, padx=5)
        tk.Label(row9, text="(可选)", font=("微软雅黑", 8), fg="gray").pack(side=tk.LEFT)
        
        # API Model
        row10 = tk.Frame(self.quiz_frame)
        row10.pack(fill=tk.X, pady=3)
        tk.Label(row10, text="API Model:", font=("微软雅黑", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.api_model_var = tk.StringVar()
        tk.Entry(row10, textvariable=self.api_model_var, font=("微软雅黑", 9), width=50).pack(side=tk.LEFT, padx=5)
        tk.Label(row10, text="(可选)", font=("微软雅黑", 8), fg="gray").pack(side=tk.LEFT)

        row10b = tk.Frame(self.quiz_frame)
        row10b.pack(fill=tk.X, pady=3)
        self.verify_api_on_start_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            row10b,
            text="启动前验证 API 可用性（可能增加启动耗时）",
            variable=self.verify_api_on_start_var,
            font=("微软雅黑", 9)
        ).pack(side=tk.LEFT, padx=5)
        
        # ==================== 运行选项 ====================
        option_frame = tk.LabelFrame(
            container,
            text="⚙️ 运行选项",
            font=("微软雅黑", 10, "bold"),
            padx=10,
            pady=8
        )
        option_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 无头模式
        row11 = tk.Frame(option_frame)
        row11.pack(fill=tk.X, pady=3)
        self.headless_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            row11,
            text="无头模式运行(不显示浏览器窗口)",
            variable=self.headless_var,
            font=("微软雅黑", 9)
        ).pack(side=tk.LEFT, padx=5)
        
        # 实时日志
        row12 = tk.Frame(option_frame)
        row12.pack(fill=tk.X, pady=3)
        self.show_realtime_log_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            row12,
            text="显示实时日志输出",
            variable=self.show_realtime_log_var,
            font=("微软雅黑", 9),
            command=self.toggle_log_visibility
        ).pack(side=tk.LEFT, padx=5)
        
        # 多实例运行
        row13 = tk.Frame(option_frame)
        row13.pack(fill=tk.X, pady=3)
        self.multi_instance_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            row13,
            text="允许多实例运行(同时运行多个账号)",
            variable=self.multi_instance_var,
            font=("微软雅黑", 9)
        ).pack(side=tk.LEFT, padx=5)
        
        # ==================== 环境检查 ====================
        env_frame = tk.LabelFrame(
            container,
            text="🔧 环境检查与配置",
            font=("微软雅黑", 10, "bold"),
            padx=10,
            pady=8
        )
        env_frame.pack(fill=tk.X, pady=(0, 10))
        
        env_buttons = tk.Frame(env_frame)
        env_buttons.pack(fill=tk.X, pady=3)
        
        tk.Button(
            env_buttons,
            text="🔍 检查环境",
            command=self.check_environment,
            font=("微软雅黑", 9),
            bg="#3498DB",
            fg="white",
            cursor="hand2",
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            env_buttons,
            text="⚙️ 一键配置环境",
            command=self.setup_environment,
            font=("微软雅黑", 9),
            bg="#27AE60",
            fg="white",
            cursor="hand2",
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            env_buttons,
            text="📋 查看依赖列表",
            command=self.show_requirements,
            font=("微软雅黑", 9),
            bg="#95A5A6",
            fg="white",
            cursor="hand2",
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        # ==================== 操作按钮 ====================
        control_frame = tk.LabelFrame(
            container,
            text="🎮 操作控制",
            font=("微软雅黑", 10, "bold"),
            padx=10,
            pady=8
        )
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        button_row = tk.Frame(control_frame)
        button_row.pack(fill=tk.X, pady=5)
        
        self.start_button = tk.Button(
            button_row,
            text="▶️ 开始运行",
            command=self.start_automation,
            font=("微软雅黑", 11, "bold"),
            bg="#27AE60",
            fg="white",
            cursor="hand2",
            width=12,
            height=2
        )
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = tk.Button(
            button_row,
            text="⏹️ 停止运行",
            command=self.stop_automation,
            font=("微软雅黑", 11, "bold"),
            bg="#E74C3C",
            fg="white",
            cursor="hand2",
            width=12,
            height=2,
            state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            button_row,
            text="💾 保存配置",
            command=self.save_config,
            font=("微软雅黑", 11, "bold"),
            bg="#3498DB",
            fg="white",
            cursor="hand2",
            width=12,
            height=2
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            button_row,
            text="📋 查看日志",
            command=self.open_log_file,
            font=("微软雅黑", 11, "bold"),
            bg="#9B59B6",
            fg="white",
            cursor="hand2",
            width=12,
            height=2
        ).pack(side=tk.LEFT, padx=5)
        
        # ==================== 日志输出 ====================
        self.log_frame = tk.LabelFrame(
            container,
            text="📋 运行日志",
            font=("微软雅黑", 10, "bold"),
            padx=10,
            pady=8
        )
        self.log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.log_text = scrolledtext.ScrolledText(
            self.log_frame,
            height=15,
            font=("Consolas", 9),
            bg="#F8F9FA",
            fg="#2C3E50",
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 初始欢迎信息
        self.log("="*70)
        self.log("🎓 欢迎使用知到自动播放器 - 图形化启动器 v1.0")
        self.log("="*70)
        self.log("📌 快速开始：")
        self.log("  1. 填写账号密码")
        self.log("  2. 选择运行模式")
        self.log("  3. 填写课程配置")
        self.log("  4. 点击【开始运行】")
        self.log("="*70)
        
        # 初始化模式显示
        self.on_mode_change()
    
    def on_mode_change(self):
        """模式切换"""
        if self.mode_var.get() == "video":
            self.video_frame.pack(fill=tk.X, pady=(0, 10))
            self.quiz_frame.pack_forget()
        else:
            self.video_frame.pack_forget()
            self.quiz_frame.pack(fill=tk.X, pady=(0, 10))
    
    def select_account_file(self):
        """选择配置文件"""
        file_path = filedialog.askopenfilename(
            title="选择账号配置文件",
            initialdir=self.launch_dir,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if file_path:
            self.current_account_file = file_path
            self.file_label.config(text=os.path.basename(file_path))
            self.load_config()
            self.log(f"✅ 已切换配置文件: {os.path.basename(file_path)}")
    
    def create_new_config(self):
        """创建新配置"""
        name = tk.simpledialog.askstring("新建配置", "请输入配置名称(例如: account2):")
        if name:
            if not name.endswith('.json'):
                name += '.json'
            new_file = os.path.join(self.launch_dir, name)
            if os.path.exists(new_file):
                messagebox.showerror("错误", "配置文件已存在！")
                return
            
            # 创建默认配置
            default_config = {
                "username": "",
                "password": "",
                "course_name": "",
                "course_url": "",
                "course_type": 1,
                "use_sidebar_layout": False,
                "max_watch_minutes": 0,
                "mode": "video",
                "quiz_type": "课程测试",
                "deepseek_api_key": "",
                "api_base_url": "",
                "api_model": "",
                "verify_api_on_start": False
            }
            
            with open(new_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
            
            self.current_account_file = new_file
            self.file_label.config(text=name)
            self.load_config()
            self.log(f"✅ 已创建新配置: {name}")
            messagebox.showinfo("成功", f"配置文件已创建: {name}")
    
    def load_config(self):
        """加载配置"""
        try:
            if os.path.exists(self.current_account_file):
                # 【修复】尝试多种编码方式
                encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312']
                config = None
                
                for encoding in encodings:
                    try:
                        with open(self.current_account_file, 'r', encoding=encoding) as f:
                            config = json.load(f)
                        self.log(f"✅ 使用 {encoding} 编码加载成功")
                        break
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                
                if config is None:
                    raise Exception("无法解析配置文件，请检查文件编码")
                
                self.username_var.set(config.get('username', ''))
                self.password_var.set(config.get('password', ''))
                self.course_name_var.set(config.get('course_name', ''))
                self.course_url_var.set(config.get('course_url', ''))  # 【新增】
                self.course_type_var.set(config.get('course_type', 1))
                self.sidebar_var.set(config.get('use_sidebar_layout', False))
                self.max_watch_minutes_var.set(config.get('max_watch_minutes', 0))
                self.mode_var.set(config.get('mode', 'video'))
                self.quiz_type_var.set(config.get('quiz_type', '课程测试'))
                self.api_key_var.set(config.get('deepseek_api_key', ''))
                self.api_base_url_var.set(config.get('api_base_url', ''))
                self.api_model_var.set(config.get('api_model', ''))
                self.verify_api_on_start_var.set(config.get('verify_api_on_start', False))
                
                self.on_mode_change()
                self.log("✅ 配置已加载")
            else:
                self.log("⚠️  配置文件不存在，请先保存配置")
        except Exception as e:
            error_msg = f"⚠️  加载配置失败: {str(e)}"
            self.log(error_msg)
            messagebox.showerror("错误", error_msg)
    
    def save_config(self):
        """保存配置"""
        try:
            config = {
                "username": self.username_var.get(),
                "password": self.password_var.get(),
                "course_name": self.course_name_var.get(),
                "course_url": self.course_url_var.get(),  # 【新增】
                "course_type": self.course_type_var.get(),
                "use_sidebar_layout": self.sidebar_var.get(),
                "max_watch_minutes": self.max_watch_minutes_var.get(),
                "mode": self.mode_var.get(),
                "quiz_type": self.quiz_type_var.get(),
                "deepseek_api_key": self.api_key_var.get(),
                "api_base_url": self.api_base_url_var.get(),
                "api_model": self.api_model_var.get(),
                "verify_api_on_start": self.verify_api_on_start_var.get(),
                "note": "知到自动播放器配置文件"
            }
            
            with open(self.current_account_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            
            self.log("✅ 配置已保存")
            messagebox.showinfo("成功", "配置已成功保存！")
        except Exception as e:
            self.log(f"❌ 保存失败: {e}")
            messagebox.showerror("错误", f"保存失败: {e}")
    
    def check_environment(self):
        """检查环境"""
        self.log("\n" + "="*70)
        self.log("🔍 开始检查环境...")
        self.log("="*70)
        
        # 检查Python版本
        python_version = sys.version.split()[0]
        self.log(f"✅ Python版本: {python_version}")
        
        # 检查依赖库
        required_libs = [
            'selenium',
            'webdriver_manager',
            'openai',
            'dotenv',
            'tenacity'
        ]
        
        for lib in required_libs:
            try:
                __import__(lib if lib != 'dotenv' else 'dotenv')
                self.log(f"✅ {lib}: 已安装")
            except ImportError:
                self.log(f"❌ {lib}: 未安装")
        
        self.log("="*70)
        self.log("✅ 环境检查完成")
        self.log("="*70 + "\n")
    
    def setup_environment(self):
        """一键配置环境"""
        if messagebox.askyesno("确认", "将自动安装所有依赖库，是否继续？"):
            self.log("\n" + "="*70)
            self.log("⚙️ 开始配置环境...")
            self.log("="*70)
            
            # 在新线程中执行
            def install():
                try:
                    requirements_file = os.path.join(self.project_root, '文档', 'requirements.txt')
                    if os.path.exists(requirements_file):
                        cmd = [sys.executable, '-m', 'pip', 'install', '-r', requirements_file]
                        self.log(f"📌 执行命令: {' '.join(cmd)}")
                        
                        # 【修复】使用系统默认编码，并捕获错误
                        process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            encoding='gbk',  # Windows下cmd默认GBK
                            errors='replace'  # 遇到无法解码的字符用?替换
                        )
                        
                        for line in process.stdout:
                            self.log(line.rstrip())
                        
                        process.wait()
                        
                        if process.returncode == 0:
                            self.log("="*70)
                            self.log("✅ 环境配置完成")
                            self.log("="*70 + "\n")
                            messagebox.showinfo("成功", "环境配置完成！")
                        else:
                            self.log("❌ 环境配置失败")
                            messagebox.showerror("错误", "环境配置失败！")
                    else:
                        self.log("❌ 未找到requirements.txt文件")
                        messagebox.showerror("错误", "未找到requirements.txt文件！")
                except Exception as e:
                    self.log(f"❌ 配置出错: {e}")
                    messagebox.showerror("错误", f"配置出错: {e}")
            
            threading.Thread(target=install, daemon=True).start()
    
    def show_requirements(self):
        """显示依赖列表"""
        requirements_file = os.path.join(self.project_root, '文档', 'requirements.txt')
        if os.path.exists(requirements_file):
            # 【修复】尝试多种编码
            encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312']
            content = None
            
            for encoding in encodings:
                try:
                    with open(requirements_file, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if content:
                messagebox.showinfo("依赖列表", content)
            else:
                messagebox.showerror("错误", "无法读取requirements.txt，请检查文件编码！")
        else:
            messagebox.showerror("错误", "未找到requirements.txt文件！")
    
    def load_system_env_config(self):
        """从系统环境变量读取DeepSeek API配置"""
        try:
            self.log("\n" + "="*70)
            self.log("🔍 开始读取系统环境配置...")
            self.log("="*70)
            
            api_key = os.getenv('DEEPSEEK_API_KEY', '').strip() or os.getenv('ANTHROPIC_AUTH_TOKEN', '').strip()
            api_base_url = os.getenv('DEEPSEEK_BASE_URL', '').strip() or os.getenv('ANTHROPIC_BASE_URL', '').strip()
            api_model = os.getenv('DEEPSEEK_MODEL', '').strip() or os.getenv('ANTHROPIC_MODEL', '').strip()
            
            found_count = 0
            
            # 填充API密钥
            if api_key:
                self.api_key_var.set(api_key)
                if os.getenv('DEEPSEEK_API_KEY', '').strip():
                    self.log("✅ DEEPSEEK_API_KEY: 已读取")
                else:
                    self.log("✅ ANTHROPIC_AUTH_TOKEN: 已读取（兼容）")
                found_count += 1
            else:
                self.log("⚠️  DEEPSEEK_API_KEY / ANTHROPIC_AUTH_TOKEN: 未设置")
            
            # 填充API Base URL
            if api_base_url:
                self.api_base_url_var.set(api_base_url)
                if os.getenv('DEEPSEEK_BASE_URL', '').strip():
                    self.log(f"✅ DEEPSEEK_BASE_URL: {api_base_url}")
                else:
                    self.log(f"✅ ANTHROPIC_BASE_URL: {api_base_url}（兼容）")
                found_count += 1
            else:
                self.log("⚠️  DEEPSEEK_BASE_URL / ANTHROPIC_BASE_URL: 未设置")
            
            # 填充API Model
            if api_model:
                self.api_model_var.set(api_model)
                if os.getenv('DEEPSEEK_MODEL', '').strip():
                    self.log(f"✅ DEEPSEEK_MODEL: {api_model}")
                else:
                    self.log(f"✅ ANTHROPIC_MODEL: {api_model}（兼容）")
                found_count += 1
            else:
                self.log("⚠️  DEEPSEEK_MODEL / ANTHROPIC_MODEL: 未设置")
            
            self.log("="*70)
            
            if found_count > 0:
                self.log(f"✅ 成功读取 {found_count} 项系统配置")
                self.log("="*70 + "\n")
                messagebox.showinfo("成功", f"已从系统环境变量读取 {found_count} 项配置！")
            else:
                self.log("⚠️  未找到任何系统配置")
                self.log("="*70 + "\n")
                messagebox.showwarning(
                    "提示", 
                    "未找到系统环境配置！\n\n"
                    "请设置以下环境变量：\n"
                    "  - DEEPSEEK_API_KEY（必需，优先）\n"
                    "  - DEEPSEEK_BASE_URL（可选，优先）\n"
                    "  - DEEPSEEK_MODEL（可选，优先）\n"
                    "兼容旧变量：ANTHROPIC_AUTH_TOKEN / ANTHROPIC_BASE_URL / ANTHROPIC_MODEL"
                )
        
        except Exception as e:
            error_msg = f"❌ 读取系统配置失败: {str(e)}"
            self.log(error_msg)
            messagebox.showerror("错误", error_msg)
    
    def validate_config(self):
        """验证配置"""
        if not self.username_var.get().strip():
            messagebox.showerror("错误", "请填写用户名！")
            return False
        
        if not self.password_var.get().strip():
            messagebox.showerror("错误", "请填写密码！")
            return False
        
        has_course_name = bool(self.course_name_var.get().strip())
        has_course_url = bool(self.course_url_var.get().strip())
        if not has_course_name and not has_course_url:
            messagebox.showerror("错误", "请填写课程名称或课程URL！")
            return False
        
        if self.mode_var.get() == "quiz_only" and not self.api_key_var.get().strip():
            messagebox.showerror("错误", "答题模式需要填写DeepSeek API密钥！")
            return False
        
        return True
    
    def start_automation(self):
        """开始运行"""
        if not self.validate_config():
            return
        
        # 保存配置
        self.save_config()
        
        # 更新按钮状态
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.is_running = True
        
        # 清空日志
        if self.show_realtime_log_var.get():
            self.log_text.delete(1.0, tk.END)
        
        self.log("\n" + "="*70)
        self.log("🚀 开始运行自动化任务...")
        self.log("="*70)
        
        # 在新线程中运行
        threading.Thread(target=self.run_automation, daemon=True).start()
    
    def run_automation(self):
        """运行自动化"""
        try:
            launcher_path = os.path.join(self.code_dir, 'zhidao_launcher.py')
            cmd = [
                sys.executable,
                launcher_path,
                '--account',
                self.current_account_file
            ]
            
            if self.headless_var.get():
                cmd.append('--headless')
            
            self.log(f"📌 执行命令: {' '.join(cmd)}\n")
            self.log(f"📁 工作目录: {self.code_dir}\n")
            self.log(f"📄 配置文件: {self.current_account_file}\n")
            
            # 【修复】使用UTF-8编码读取子进程输出（子进程已设置UTF-8输出）
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',  # 子进程使用UTF-8输出
                errors='replace',  # 遇到无法解码的字符用?替换
                bufsize=1,
                cwd=self.code_dir
            )
            
            self.log("✅ 进程已启动，正在运行...\n")
            
            # 【修复】无论是否显示实时日志，都要读取输出，否则进程会阻塞
            for line in self.process.stdout:
                if not self.is_running:
                    break
                # 始终读取输出，但只在勾选时显示
                line = line.rstrip()
                if line:  # 忽略空行
                    if self.show_realtime_log_var.get():
                        self.log(line)
                    else:
                        # 即使不显示，也要处理一些关键信息
                        if any(keyword in line for keyword in ['ERROR', 'CRITICAL', '错误', '失败', '异常']):
                            self.log(f"⚠️ {line}")
            
            self.process.wait()
            
            if self.is_running:
                self.log("\n" + "="*70)
                if self.process.returncode == 0:
                    self.log("✅ 任务完成")
                else:
                    self.log(f"⚠️ 任务结束（退出码: {self.process.returncode}）")
                self.log("="*70 + "\n")
        
        except Exception as e:
            self.log(f"\n❌ 运行出错: {e}\n")
            messagebox.showerror("错误", f"运行出错: {e}")
        
        finally:
            self.root.after(0, self.reset_buttons)
    
    def stop_automation(self):
        """停止运行"""
        if self.process and self.process.poll() is None:
            self.is_running = False
            self.process.terminate()
            self.log("\n⏹️ 已停止运行\n")
    
    def reset_buttons(self):
        """重置按钮"""
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.is_running = False
    
    def toggle_log_visibility(self):
        """切换日志显示"""
        if self.show_realtime_log_var.get():
            self.log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        else:
            self.log_frame.pack_forget()
    
    def open_log_file(self):
        """打开日志文件"""
        log_dir = os.path.join(self.project_root, 'log')
        if os.path.exists(log_dir):
            if sys.platform == 'win32':
                os.startfile(log_dir)
            else:
                subprocess.Popen(['xdg-open', log_dir])
        else:
            messagebox.showinfo("提示", "日志文件夹不存在！")
    
    def log(self, message):
        """输出日志"""
        def append():
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
        
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, append)
        else:
            append()
    
    def update_log(self):
        """更新日志（定时任务）"""
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log(msg)
        except queue.Empty:
            pass
        
        self.root.after(100, self.update_log)


def main():
    """主函数"""
    root = tk.Tk()
    
    # 导入askstring对话框
    import tkinter.simpledialog
    tk.simpledialog = tkinter.simpledialog
    
    app = ZhidaoGUILauncher(root)
    root.mainloop()


if __name__ == '__main__':
    main()

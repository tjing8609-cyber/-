#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Copyright (c) 2025 景潼
Zhidao Auto is licensed under Mulan PSL v2.

知到自动播放器 - 图形化启动界面
为无代码基础用户提供简单易用的操作界面
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import os
import sys
import threading
import subprocess

# 添加code文件夹到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
code_dir = os.path.join(project_root, 'code')
if code_dir not in sys.path:
    sys.path.insert(0, code_dir)


class ZhidaoGUILauncher:
    """知到自动播放器图形化启动器"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("知到自动播放器 - 图形化启动界面 v1.0")
        self.root.geometry("700x850")
        self.root.resizable(False, False)
        
        # 配置文件路径
        self.config_dir = os.path.dirname(os.path.abspath(__file__))
        self.account_file = os.path.join(self.config_dir, 'account.json')
        
        # 运行状态
        self.is_running = False
        self.process = None
        
        # 创建界面
        self.create_widgets()
        
        # 加载配置
        self.load_config()
    
    def create_widgets(self):
        """创建界面组件"""
        
        # ==================== 标题区域 ====================
        title_frame = tk.Frame(self.root, bg="#2C3E50", height=60)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame,
            text="🎓 知到自动播放器",
            font=("微软雅黑", 18, "bold"),
            bg="#2C3E50",
            fg="white"
        )
        title_label.pack(pady=15)
        
        # ==================== 主容器 ====================
        main_container = tk.Frame(self.root, padx=20, pady=20)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # ==================== 账号配置区域 ====================
        account_frame = tk.LabelFrame(
            main_container,
            text="📝 账号配置",
            font=("微软雅黑", 11, "bold"),
            padx=15,
            pady=10
        )
        account_frame.pack(fill=tk.X, pady=(0, 15))
        
        # 用户名
        tk.Label(account_frame, text="用户名:", font=("微软雅黑", 10)).grid(row=0, column=0, sticky=tk.W, pady=5)
        self.username_var = tk.StringVar()
        tk.Entry(account_frame, textvariable=self.username_var, width=40, font=("微软雅黑", 10)).grid(row=0, column=1, pady=5, padx=(10, 0))
        
        # 密码
        tk.Label(account_frame, text="密码:", font=("微软雅黑", 10)).grid(row=1, column=0, sticky=tk.W, pady=5)
        self.password_var = tk.StringVar()
        tk.Entry(account_frame, textvariable=self.password_var, show="*", width=40, font=("微软雅黑", 10)).grid(row=1, column=1, pady=5, padx=(10, 0))
        
        # ==================== 运行模式区域 ====================
        mode_frame = tk.LabelFrame(
            main_container,
            text="🎯 运行模式",
            font=("微软雅黑", 11, "bold"),
            padx=15,
            pady=10
        )
        mode_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.mode_var = tk.StringVar(value="video")
        
        # 视频播放模式
        video_radio = tk.Radiobutton(
            mode_frame,
            text="📹 视频播放模式（观看视频）",
            variable=self.mode_var,
            value="video",
            font=("微软雅黑", 10),
            command=self.on_mode_change
        )
        video_radio.grid(row=0, column=0, sticky=tk.W, pady=5)
        
        # 纯答题模式
        quiz_radio = tk.Radiobutton(
            mode_frame,
            text="📝 纯答题模式（只答题不看视频）",
            variable=self.mode_var,
            value="quiz_only",
            font=("微软雅黑", 10),
            command=self.on_mode_change
        )
        quiz_radio.grid(row=1, column=0, sticky=tk.W, pady=5)
        
        # ==================== 视频模式配置 ====================
        self.video_config_frame = tk.LabelFrame(
            main_container,
            text="📹 视频模式配置",
            font=("微软雅黑", 11, "bold"),
            padx=15,
            pady=10
        )
        self.video_config_frame.pack(fill=tk.X, pady=(0, 15))
        
        # 课程名称
        tk.Label(self.video_config_frame, text="课程名称:", font=("微软雅黑", 10)).grid(row=0, column=0, sticky=tk.W, pady=5)
        self.course_name_var = tk.StringVar()
        tk.Entry(self.video_config_frame, textvariable=self.course_name_var, width=40, font=("微软雅黑", 10)).grid(row=0, column=1, pady=5, padx=(10, 0))
        
        # 课程类型
        tk.Label(self.video_config_frame, text="课程类型:", font=("微软雅黑", 10)).grid(row=1, column=0, sticky=tk.W, pady=5)
        self.course_type_var = tk.IntVar(value=1)
        course_type_frame = tk.Frame(self.video_config_frame)
        course_type_frame.grid(row=1, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        tk.Radiobutton(
            course_type_frame,
            text="无题目",
            variable=self.course_type_var,
            value=1,
            font=("微软雅黑", 9)
        ).pack(side=tk.LEFT, padx=(0, 15))
        
        tk.Radiobutton(
            course_type_frame,
            text="有题目（自动关闭）",
            variable=self.course_type_var,
            value=2,
            font=("微软雅黑", 9)
        ).pack(side=tk.LEFT)
        
        # 观看时长限制
        tk.Label(self.video_config_frame, text="观看时长(分钟):", font=("微软雅黑", 10)).grid(row=2, column=0, sticky=tk.W, pady=5)
        watch_frame = tk.Frame(self.video_config_frame)
        watch_frame.grid(row=2, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        self.max_watch_minutes_var = tk.IntVar(value=0)
        tk.Spinbox(
            watch_frame,
            from_=0,
            to=999,
            textvariable=self.max_watch_minutes_var,
            width=10,
            font=("微软雅黑", 10)
        ).pack(side=tk.LEFT)
        
        tk.Label(watch_frame, text="(0=播放全部)", font=("微软雅黑", 9), fg="gray").pack(side=tk.LEFT, padx=(10, 0))
        
        # ==================== 答题模式配置 ====================
        self.quiz_config_frame = tk.LabelFrame(
            main_container,
            text="📝 答题模式配置",
            font=("微软雅黑", 11, "bold"),
            padx=15,
            pady=10
        )
        self.quiz_config_frame.pack(fill=tk.X, pady=(0, 15))
        
        # 课程名称（答题模式）
        tk.Label(self.quiz_config_frame, text="课程名称:", font=("微软雅黑", 10)).grid(row=0, column=0, sticky=tk.W, pady=5)
        self.quiz_course_name_var = tk.StringVar()
        tk.Entry(self.quiz_config_frame, textvariable=self.quiz_course_name_var, width=40, font=("微软雅黑", 10)).grid(row=0, column=1, pady=5, padx=(10, 0))
        
        # 测试类型
        tk.Label(self.quiz_config_frame, text="测试类型:", font=("微软雅黑", 10)).grid(row=1, column=0, sticky=tk.W, pady=5)
        self.quiz_type_var = tk.StringVar(value="课程测试")
        quiz_type_combo = ttk.Combobox(
            self.quiz_config_frame,
            textvariable=self.quiz_type_var,
            values=["课程测试", "章节测试", "单元测试", "期末考试"],
            width=37,
            font=("微软雅黑", 10),
            state="readonly"
        )
        quiz_type_combo.grid(row=1, column=1, pady=5, padx=(10, 0))
        
        # DeepSeek API密钥
        tk.Label(self.quiz_config_frame, text="DeepSeek API:", font=("微软雅黑", 10)).grid(row=2, column=0, sticky=tk.W, pady=5)
        self.api_key_var = tk.StringVar()
        tk.Entry(self.quiz_config_frame, textvariable=self.api_key_var, width=40, font=("微软雅黑", 10), show="*").grid(row=2, column=1, pady=5, padx=(10, 0))
        
        tk.Label(
            self.quiz_config_frame,
            text="提示: 答题模式需要DeepSeek API密钥（必填）",
            font=("微软雅黑", 8),
            fg="orange"
        ).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))
        
        # ==================== 操作按钮区域 ====================
        button_frame = tk.Frame(main_container)
        button_frame.pack(fill=tk.X, pady=(0, 15))
        
        # 开始按钮
        self.start_button = tk.Button(
            button_frame,
            text="▶️ 开始运行",
            command=self.start_automation,
            font=("微软雅黑", 12, "bold"),
            bg="#27AE60",
            fg="white",
            activebackground="#229954",
            activeforeground="white",
            relief=tk.RAISED,
            bd=3,
            width=15,
            height=2,
            cursor="hand2"
        )
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        # 停止按钮
        self.stop_button = tk.Button(
            button_frame,
            text="⏸️ 停止运行",
            command=self.stop_automation,
            font=("微软雅黑", 12, "bold"),
            bg="#E74C3C",
            fg="white",
            activebackground="#C0392B",
            activeforeground="white",
            relief=tk.RAISED,
            bd=3,
            width=15,
            height=2,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # 保存配置按钮
        save_button = tk.Button(
            button_frame,
            text="💾 保存配置",
            command=self.save_config,
            font=("微软雅黑", 11),
            bg="#3498DB",
            fg="white",
            activebackground="#2980B9",
            activeforeground="white",
            relief=tk.RAISED,
            bd=2,
            width=12,
            height=2,
            cursor="hand2"
        )
        save_button.pack(side=tk.LEFT, padx=5)
        
        # ==================== 日志输出区域 ====================
        log_frame = tk.LabelFrame(
            main_container,
            text="📋 运行日志",
            font=("微软雅黑", 11, "bold"),
            padx=10,
            pady=10
        )
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=12,
            font=("Consolas", 9),
            bg="#F5F5F5",
            fg="#2C3E50",
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 初始欢迎信息
        self.log("=" * 60)
        self.log("欢迎使用知到自动播放器！")
        self.log("=" * 60)
        self.log("📌 使用步骤：")
        self.log("1. 填写账号密码")
        self.log("2. 选择运行模式（视频播放 或 纯答题）")
        self.log("3. 填写对应配置信息")
        self.log("4. 点击【开始运行】")
        self.log("=" * 60)
        
        # 初始化模式显示
        self.on_mode_change()
    
    def on_mode_change(self):
        """模式切换时的处理"""
        mode = self.mode_var.get()
        
        if mode == "video":
            # 显示视频配置，隐藏答题配置
            self.video_config_frame.pack(fill=tk.X, pady=(0, 15))
            self.quiz_config_frame.pack_forget()
        else:
            # 显示答题配置，隐藏视频配置
            self.video_config_frame.pack_forget()
            self.quiz_config_frame.pack(fill=tk.X, pady=(0, 15))
    
    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.account_file):
                with open(self.account_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 加载账号信息
                self.username_var.set(config.get('username', ''))
                self.password_var.set(config.get('password', ''))
                
                # 加载模式
                mode = config.get('mode', 'video')
                self.mode_var.set(mode)
                
                # 加载视频模式配置
                self.course_name_var.set(config.get('course_name', ''))
                self.course_type_var.set(config.get('course_type', 1))
                self.max_watch_minutes_var.set(config.get('max_watch_minutes', 0))
                
                # 加载答题模式配置
                self.quiz_course_name_var.set(config.get('course_name', ''))
                self.quiz_type_var.set(config.get('quiz_type', '课程测试'))
                self.api_key_var.set(config.get('deepseek_api_key', ''))
                
                self.log("✅ 已加载配置文件")
                
                # 更新界面显示
                self.on_mode_change()
        except Exception as e:
            self.log(f"⚠️ 加载配置失败: {e}")
    
    def save_config(self):
        """保存配置到文件"""
        try:
            mode = self.mode_var.get()
            
            # 根据模式选择课程名称
            if mode == "video":
                course_name = self.course_name_var.get()
            else:
                course_name = self.quiz_course_name_var.get()
            
            config = {
                "username": self.username_var.get(),
                "password": self.password_var.get(),
                "course_name": course_name,
                "course_type": self.course_type_var.get(),
                "use_sidebar_layout": False,
                "max_watch_minutes": self.max_watch_minutes_var.get(),
                "mode": mode,
                "quiz_type": self.quiz_type_var.get(),
                "deepseek_api_key": self.api_key_var.get(),
                "api_base_url": "",
                "api_model": "",
                "note": "知到自动播放器配置文件",
                "course_type_note": "课程类型: 1=无题目课程, 2=有题目课程",
                "mode_note": "运行模式: video=视频播放模式, quiz_only=纯答题模式",
                "quiz_type_note": "测试类型: 课程测试/章节测试/单元测试/期末考试"
            }
            
            with open(self.account_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            
            self.log("✅ 配置已保存")
            messagebox.showinfo("成功", "配置已成功保存！")
            
        except Exception as e:
            self.log(f"❌ 保存配置失败: {e}")
            messagebox.showerror("错误", f"保存配置失败：{e}")
    
    def validate_config(self):
        """验证配置是否完整"""
        # 检查账号密码
        if not self.username_var.get().strip():
            messagebox.showerror("错误", "请填写用户名！")
            return False
        
        if not self.password_var.get().strip():
            messagebox.showerror("错误", "请填写密码！")
            return False
        
        mode = self.mode_var.get()
        
        if mode == "video":
            # 视频模式检查
            if not self.course_name_var.get().strip():
                messagebox.showerror("错误", "请填写课程名称！")
                return False
        else:
            # 答题模式检查
            if not self.quiz_course_name_var.get().strip():
                messagebox.showerror("错误", "请填写课程名称！")
                return False
            
            if not self.api_key_var.get().strip():
                messagebox.showerror("错误", "答题模式需要填写DeepSeek API密钥！")
                return False
        
        return True
    
    def start_automation(self):
        """开始自动化运行"""
        # 验证配置
        if not self.validate_config():
            return
        
        # 保存配置
        self.save_config()
        
        # 更新按钮状态
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.is_running = True
        
        # 清空日志
        self.log_text.delete(1.0, tk.END)
        self.log("=" * 60)
        self.log("🚀 开始运行自动化任务...")
        self.log("=" * 60)
        
        # 在新线程中运行
        thread = threading.Thread(target=self.run_automation, daemon=True)
        thread.start()
    
    def run_automation(self):
        """运行自动化任务（在子线程中执行）"""
        try:
            # 构建命令
            launcher_path = os.path.join(os.path.dirname(self.config_dir), 'code', 'zhidao_launcher.py')
            cmd = [
                sys.executable,
                launcher_path,
                '--account',
                self.account_file
            ]
            
            self.log(f"📌 执行命令: {' '.join(cmd)}")
            self.log("")
            
            # 运行进程
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                bufsize=1,
                cwd=os.path.dirname(launcher_path)
            )
            
            # 实时读取输出
            for line in self.process.stdout:
                if not self.is_running:
                    break
                self.log(line.rstrip())
            
            self.process.wait()
            
            if self.is_running:
                self.log("")
                self.log("=" * 60)
                self.log("✅ 任务完成")
                self.log("=" * 60)
            
        except Exception as e:
            self.log(f"❌ 运行出错: {e}")
            messagebox.showerror("错误", f"运行出错：{e}")
        
        finally:
            # 重置状态
            self.root.after(0, self.reset_buttons)
    
    def stop_automation(self):
        """停止自动化运行"""
        if self.process and self.process.poll() is None:
            self.is_running = False
            self.process.terminate()
            self.log("")
            self.log("⏸️ 已停止运行")
            self.log("=" * 60)
    
    def reset_buttons(self):
        """重置按钮状态"""
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.is_running = False
    
    def log(self, message):
        """在日志区域显示消息"""
        def append():
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
        
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, append)
        else:
            append()


def main():
    """主函数"""
    root = tk.Tk()
    app = ZhidaoGUILauncher(root)
    root.mainloop()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
连点器 Pro (Auto Clicker Pro) - 高级屏幕点击自动化工具

功能：
  1. 单点点击 - 坐标输入/取点，设置次数/间隔/速度
  2. 操作录制 - 录制点击操作并复现
  3. 录制管理 - 保存/重命名/删除录制
  4. 高级模式 - 可视化流程编辑器，支持截图匹配、分支逻辑、循环跳转

快捷键：F6 开始/停止 | Esc 取消
安全退出：鼠标移至屏幕左上角
"""

# Windows 高DPI感知：必须在 tkinter/pyautogui 导入之前设置
if sys.platform == 'win32':
    try:
        import ctypes
        # Per-Monitor DPI Aware (Win8.1+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, colorchooser
import threading
import time
import json
import os
import sys
import subprocess
import uuid
import copy
import random
import math
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable, Tuple

# 单文件打包时 __file__ 在临时目录，用 EXE 所在目录代替
_APP_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent

# ═══════════════════════════════════════════════════════════════
#  多显示器工具
# ═══════════════════════════════════════════════════════════════
def _get_virtual_screen_rect():
    """获取所有显示器组成的虚拟屏幕边界 (left, top, width, height)
    坐标系原点在主显示器左上角，副显示器可能有负坐标。"""
    if sys.platform == 'win32':
        try:
            import ctypes
            SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
            SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
            left   = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
            top    = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
            width  = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
            height = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
            return (left, top, width, height)
        except Exception:
            pass
    # fallback: 仅主显示器
    return (0, 0, _get_primary_screen_size()[0], _get_primary_screen_size()[1])

def _get_primary_screen_size():
    """获取主显示器分辨率 (width, height)"""
    if sys.platform == 'win32':
        try:
            import ctypes
            w = ctypes.windll.user32.GetSystemMetrics(0)  # SM_CXSCREEN
            h = ctypes.windll.user32.GetSystemMetrics(1)  # SM_CYSCREEN
            return (w, h)
        except Exception:
            pass
    import tkinter as _tk
    _r = _tk.Tk()
    _r.withdraw()
    w, h = _r.winfo_screenwidth(), _r.winfo_screenheight()
    _r.destroy()
    return (w, h)

def _screenshot_virtual_screen():
    """截取整个虚拟屏幕（所有显示器），返回 (PIL.Image, (left, top))"""
    from PIL import ImageGrab
    rect = _get_virtual_screen_rect()
    left, top, width, height = rect
    img = ImageGrab.grab(bbox=(left, top, left + width, top + height))
    return img, (left, top)

def _create_fullscreen_window(parent, alpha=0.01):
    """创建覆盖所有显示器的全屏透明窗口，返回 (Toplevel, canvas)"""
    import tkinter as _tk
    rect = _get_virtual_screen_rect()
    left, top, width, height = rect
    
    win = _tk.Toplevel(parent)
    # 无边框 + 位置覆盖整个虚拟屏幕
    win.overrideredirect(True)
    win.geometry(f"{width}x{height}+{left}+{top}")
    win.attributes('-topmost', True)
    win.attributes('-alpha', alpha)
    win.configure(bg='black')
    
    canvas = _tk.Canvas(win, bg='black', highlightthickness=0, 
                        width=width, height=height)
    canvas.pack(fill='both', expand=True)
    
    return win, canvas, (left, top)

# ═══════════════════════════════════════════════════════════════
#  依赖自动安装
# ═══════════════════════════════════════════════════════════════
def _ensure_deps():
    """检查并自动安装依赖"""
    missing = []
    for mod, pkg in [('pyautogui', 'pyautogui'), 
                     ('pynput', 'pynput'),
                     ('PIL', 'Pillow'),
                     ('cv2', 'opencv-python'),
                     ('numpy', 'numpy')]:
        try:
            if mod == 'cv2':
                __import__('cv2')
            elif mod == 'PIL':
                __import__('PIL')
            else:
                __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"正在安装依赖: {', '.join(missing)} ...")
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install'] + missing + ['-q']
        )
        print("依赖安装完成！")

_ensure_deps()

import pyautogui
from pynput import mouse as pynput_mouse
from pynput import keyboard as pynput_keyboard
import cv2
import numpy as np
from PIL import Image, ImageTk, ImageDraw

# pyautogui 安全设置
pyautogui.FAILSAFE = True

# pynput 特殊键 → pyautogui 按键名 映射
# 修饰键统一映射（左右都映射到同一个标准名，供 hotkey 使用）
_MODIFIER_UNIFY = {
    'Key.shift_l': 'Key.shift', 'Key.shift_r': 'Key.shift',
    'Key.ctrl_l':  'Key.ctrl',  'Key.ctrl_r':  'Key.ctrl',
    'Key.alt_l':   'Key.alt',   'Key.alt_r':   'Key.alt',
    'Key.alt_gr':  'Key.alt',
    'Key.cmd_l':   'Key.cmd',   'Key.cmd_r':   'Key.cmd',
}

_PYNPUT_KEY_MAP = {
    'Key.space':     'space',
    'Key.enter':     'enter',
    'Key.tab':       'tab',
    'Key.esc':       'esc',
    'Key.shift':     'shift',
    'Key.shift_l':   'shiftleft',
    'Key.shift_r':   'shiftright',
    'Key.ctrl':      'ctrl',
    'Key.ctrl_l':    'ctrlleft',
    'Key.ctrl_r':    'ctrlright',
    'Key.alt':       'alt',
    'Key.alt_l':     'altleft',
    'Key.alt_r':     'altright',
    'Key.alt_gr':    'alt',
    'Key.backspace': 'backspace',
    'Key.delete':    'delete',
    'Key.insert':    'insert',
    'Key.home':      'home',
    'Key.end':       'end',
    'Key.up':        'up',
    'Key.down':      'down',
    'Key.left':      'left',
    'Key.right':     'right',
    'Key.page_up':   'pageup',
    'Key.page_down': 'pagedown',
    'Key.caps_lock': 'capslock',
    'Key.num_lock':  'numlock',
    'Key.scroll_lock':'scrolllock',
    'Key.f1':  'f1',  'Key.f2':  'f2',  'Key.f3':  'f3',  'Key.f4':  'f4',
    'Key.f5':  'f5',  'Key.f6':  'f6',  'Key.f7':  'f7',  'Key.f8':  'f8',
    'Key.f9':  'f9',  'Key.f10': 'f10', 'Key.f11': 'f11', 'Key.f12': 'f12',
    'Key.cmd':       'win',
    'Key.cmd_l':     'winleft',
    'Key.cmd_r':     'winright',
    'Key.print_screen': 'printscreen',
    'Key.pause':     'pause',
    'Key.menu':      'apps',
}

def _resolve_key(key_str):
    """将 pynput 格式的按键名转换为 pyautogui 可识别的按键名。"""
    mapped = _PYNPUT_KEY_MAP.get(key_str)
    if mapped:
        return mapped
    # 普通字符键直接返回
    return key_str
pyautogui.PAUSE  = 0.005  # 原值0.001过小，可能导致操作过快出错

# ═══════════════════════════════════════════════════════════════
#  常量
# ═══════════════════════════════════════════════════════════════
NODE_WIDTH = 180
NODE_HEIGHT = 100
NODE_COLORS = {
    'normal': '#E3F2FD',      # 浅蓝 - 主线节点
    'branch': '#FFF3E0',      # 浅橙 - 分支节点
    'active': '#81C784',      # 深绿 - 当前执行
    'selected': '#FFEB3B',    # 黄色 - 选中
    'disconnected': '#E0E0E0' # 灰色 - 未连线
}

# 操作类型
OP_CLICK = 'click'
OP_DOUBLE_CLICK = 'double_click'
OP_KEY = 'key'
OP_COMBO_KEY = 'combo_key'
OP_SCROLL = 'scroll'
OP_MIDDLE_CLICK = 'middle_click'
OP_WAIT = 'wait'
OP_DRAG = 'drag'  # 拖动操作

OP_NAMES = {
    OP_CLICK: '单击',
    OP_DOUBLE_CLICK: '双击',
    OP_KEY: '按键',
    OP_COMBO_KEY: '组合键',
    OP_SCROLL: '滚轮',
    OP_MIDDLE_CLICK: '中键',
    OP_WAIT: '等待',
    OP_DRAG: '拖动'
}

# 匹配方式
MATCH_POSITION = 'position'
MATCH_IMAGE = 'image'

# 匹配范围
SCOPE_FULLSCREEN = 'fullscreen'
SCOPE_SINGLE_SCREEN = 'single_screen'


# ═══════════════════════════════════════════════════════════════
#  FlowStep - 流程步骤数据结构
# ═══════════════════════════════════════════════════════════════
class FlowStep:
    """单个流程步骤"""
    
    def __init__(self, step_id: str = None):
        self.id = step_id or str(uuid.uuid4())[:8]
        self.description = ""
        
        # 匹配设置
        self.match_type = MATCH_POSITION  # position / image
        self.match_position = (0, 0)      # 精确坐标
        self.match_image_path = ""        # 截图模板路径
        self.match_image_data = None      # 截图数据 (numpy array)
        self.match_region = None          # (x, y, w, h) 搜索区域
        self.match_threshold = 0.8        # 匹配阈值 0-1
        self.match_scope = SCOPE_FULLSCREEN
        
        # 操作设置
        self.operation = OP_CLICK
        self.click_position = None        # None = 匹配位置, 或 (x, y)
        self.click_button = 'left'
        self.key_code = ""                # 单键
        self.combo_keys = []              # ['ctrl', 'shift', 'a']
        self.scroll_amount = 0            # 正数向上，负数向下
        self.click_radius = 0             # 容错半径(像素), 0=精确点击
        # 拖动操作设置
        self.drag_start = None            # (x, y) 拖动起点
        self.drag_end = None              # (x, y) 拖动终点
        self.drag_duration = 0.5          # 拖动持续时间(秒)
        self.drag_use_match_as_start = True  # 使用匹配位置作为起点
        
        # 延时设置
        self.delay_after = 100            # 步骤后延时 ms
        self.timeout = 10000              # 等待匹配超时 ms
        
        # 分支
        self.branch_enabled = False
        self.branch_type = 'condition'  # 'condition'=条件跳转, 'always'=无条件跳转
        self.branch_match_next = None     # 匹配成功跳转的步骤ID
        self.branch_nomatch_next = None   # 未匹配跳转的步骤ID
        self.branch_always_next = None    # 无条件跳转的步骤ID
        
        # UI状态
        self.canvas_x = 0
        self.canvas_y = 0
        self.is_mainline = True           # 是否在主线
        
    def to_dict(self) -> dict:
        """序列化为字典"""
        d = {
            'id': self.id,
            'description': self.description,
            'match_type': self.match_type,
            'match_position': self.match_position,
            'match_image_path': self.match_image_path,
            'match_region': self.match_region,
            'match_threshold': self.match_threshold,
            'match_scope': self.match_scope,
            'operation': self.operation,
            'click_position': self.click_position,
            'click_button': self.click_button,
            'key_code': self.key_code,
            'combo_keys': self.combo_keys,
            'scroll_amount': self.scroll_amount,
            'click_radius': self.click_radius,
            'drag_start': self.drag_start,
            'drag_end': self.drag_end,
            'drag_duration': self.drag_duration,
            'drag_use_match_as_start': self.drag_use_match_as_start,
            'delay_after': self.delay_after,
            'timeout': self.timeout,
            'branch_enabled': self.branch_enabled,
            'branch_type': self.branch_type,
            'branch_match_next': self.branch_match_next,
            'branch_nomatch_next': self.branch_nomatch_next,
            'branch_always_next': self.branch_always_next,
            'canvas_x': self.canvas_x,
            'canvas_y': self.canvas_y,
            'is_mainline': self.is_mainline
        }
        # 保存截图数据为base64
        if self.match_image_data is not None:
            _, buffer = cv2.imencode('.png', self.match_image_data)
            d['match_image_data'] = base64.b64encode(buffer).decode('utf-8')
        else:
            d['match_image_data'] = None
        return d
    
    @classmethod
    def from_dict(cls, d: dict) -> 'FlowStep':
        """从字典反序列化"""
        step = cls(step_id=d.get('id'))
        step.description = d.get('description', '')
        step.match_type = d.get('match_type', MATCH_POSITION)
        step.match_position = tuple(d.get('match_position', (0, 0)))
        step.match_image_path = d.get('match_image_path', '')
        step.match_region = tuple(d.get('match_region')) if d.get('match_region') else None
        step.match_threshold = d.get('match_threshold', 0.8)
        step.match_scope = d.get('match_scope', SCOPE_FULLSCREEN)
        step.operation = d.get('operation', OP_CLICK)
        step.click_position = tuple(d.get('click_position')) if d.get('click_position') else None
        step.click_button = d.get('click_button', 'left')
        step.key_code = d.get('key_code', '')
        step.combo_keys = d.get('combo_keys', [])
        step.scroll_amount = d.get('scroll_amount', 0)
        step.click_radius = d.get('click_radius', 0)
        step.drag_start = tuple(d.get('drag_start')) if d.get('drag_start') else None
        step.drag_end = tuple(d.get('drag_end')) if d.get('drag_end') else None
        step.drag_duration = d.get('drag_duration', 0.5)
        step.drag_use_match_as_start = d.get('drag_use_match_as_start', True)
        step.delay_after = d.get('delay_after', 100)
        step.timeout = d.get('timeout', 10000)
        step.branch_enabled = d.get('branch_enabled', False)
        step.branch_type = d.get('branch_type', 'condition')
        step.branch_match_next = d.get('branch_match_next')
        step.branch_nomatch_next = d.get('branch_nomatch_next')
        step.branch_always_next = d.get('branch_always_next')
        step.canvas_x = d.get('canvas_x', 0)
        step.canvas_y = d.get('canvas_y', 0)
        step.is_mainline = d.get('is_mainline', True)
        
        # 加载截图数据
        if d.get('match_image_data'):
            try:
                img_data = base64.b64decode(d['match_image_data'])
                nparr = np.frombuffer(img_data, np.uint8)
                step.match_image_data = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            except Exception:
                step.match_image_data = None
        return step


# ═══════════════════════════════════════════════════════════════
#  FlowProject - 流程项目
# ═══════════════════════════════════════════════════════════════
class FlowProject:
    """流程项目，管理所有步骤"""
    
    def __init__(self):
        self.steps: Dict[str, FlowStep] = {}
        self.mainline_order: List[str] = []  # 主线步骤ID顺序
        self.name = "未命名流程"
        self.created = datetime.now().isoformat()
        self.modified = datetime.now().isoformat()
        
    def add_step(self, step: FlowStep, after_id: str = None):
        """添加步骤"""
        self.steps[step.id] = step
        if step.is_mainline:
            if after_id and after_id in self.mainline_order:
                idx = self.mainline_order.index(after_id) + 1
                self.mainline_order.insert(idx, step.id)
            else:
                self.mainline_order.append(step.id)
        self.modified = datetime.now().isoformat()
        
    def remove_step(self, step_id: str):
        """删除步骤"""
        if step_id in self.steps:
            del self.steps[step_id]
        if step_id in self.mainline_order:
            self.mainline_order.remove(step_id)
        # 清除引用
        for step in self.steps.values():
            if step.branch_match_next == step_id:
                step.branch_match_next = None
            if step.branch_nomatch_next == step_id:
                step.branch_nomatch_next = None
        self.modified = datetime.now().isoformat()
        
    def get_step(self, step_id: str) -> Optional[FlowStep]:
        return self.steps.get(step_id)
    
    def get_mainline_steps(self) -> List[FlowStep]:
        return [self.steps[sid] for sid in self.mainline_order if sid in self.steps]
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'created': self.created,
            'modified': self.modified,
            'mainline_order': self.mainline_order,
            'steps': {sid: step.to_dict() for sid, step in self.steps.items()}
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> 'FlowProject':
        proj = cls()
        proj.name = d.get('name', '未命名流程')
        proj.created = d.get('created', datetime.now().isoformat())
        proj.modified = d.get('modified', datetime.now().isoformat())
        proj.mainline_order = d.get('mainline_order', [])
        proj.steps = {sid: FlowStep.from_dict(sd) for sid, sd in d.get('steps', {}).items()}
        return proj


# ═══════════════════════════════════════════════════════════════
#  FlowEngine - 流程执行引擎
# ═══════════════════════════════════════════════════════════════
class FlowEngine:
    """流程执行引擎"""
    
    def __init__(self):
        self._running = False
        self._lock = threading.Lock()
        self._current_step_id = None
        
    @property
    def running(self):
        with self._lock:
            return self._running
    
    @property
    def current_step_id(self):
        with self._lock:
            return self._current_step_id
        
    def stop(self):
        with self._lock:
            self._running = False
            
    def run(self, project: FlowProject, 
            on_step_start: Callable = None,
            on_step_done: Callable = None,
            on_done: Callable = None):
        """执行流程"""
        with self._lock:
            if self._running:
                return
            self._running = True
            
        threading.Thread(
            target=self._run_loop,
            args=(project, on_step_start, on_step_done, on_done),
            daemon=True
        ).start()
        
    def _run_loop(self, project, on_step_start, on_step_done, on_done):
        err = None
        try:
            # 从主线第一个开始
            if not project.mainline_order:
                err = "流程为空，没有可执行的步骤"
                return
            current_id = project.mainline_order[0]
            step_visits = {}  # step_id -> visit_count，防止无限循环
            MAX_VISITS_PER_STEP = 50  # 每个步骤最多执行50次
            
            while self._running:
                # 检查循环次数
                visit_count = step_visits.get(current_id, 0) + 1
                step_visits[current_id] = visit_count
                if visit_count > MAX_VISITS_PER_STEP:
                    err = f"步骤 {current_id} 已执行 {MAX_VISITS_PER_STEP} 次，可能存在无限循环"
                    break
                    
                with self._lock:
                    self._current_step_id = current_id
                    
                step = project.get_step(current_id)
                if not step:
                    break
                    
                # 回调
                if on_step_start:
                    self._safe_call(on_step_start, step.id)
                
                # 执行步骤
                success, next_id = self._execute_step(step, project)
                
                if on_step_done:
                    self._safe_call(on_step_done, step.id, success)
                    
                # 延时
                if step.delay_after > 0:
                    time.sleep(step.delay_after / 1000.0)
                    
                # 确定下一步
                if next_id:
                    current_id = next_id
                elif step.branch_enabled:
                    # 分支模式
                    if step.branch_type == 'always' and step.branch_always_next:
                        # 无条件跳转
                        current_id = step.branch_always_next
                    elif success and step.branch_match_next:
                        current_id = step.branch_match_next
                    elif not success and step.branch_nomatch_next:
                        current_id = step.branch_nomatch_next
                    else:
                        current_id = self._get_next_mainline(project, current_id)
                else:
                    current_id = self._get_next_mainline(project, current_id)
                    
                if not current_id:
                    break
                    
        except pyautogui.FailSafeException:
            err = "安全退出：鼠标已移至屏幕左上角"
        except Exception as e:
            err = str(e)
        finally:
            with self._lock:
                self._running = False
                self._current_step_id = None
            if on_done:
                self._safe_call(on_done, err)
                
    def _safe_call(self, func, *args):
        try:
            func(*args)
        except Exception:
            pass
            
    def _get_next_mainline(self, project: FlowProject, current_id: str) -> Optional[str]:
        """获取主线下一个步骤"""
        try:
            idx = project.mainline_order.index(current_id)
            if idx + 1 < len(project.mainline_order):
                return project.mainline_order[idx + 1]
        except ValueError:
            pass
        return None
        
    def _execute_step(self, step: FlowStep, project: FlowProject) -> Tuple[bool, Optional[str]]:
        """执行单个步骤，返回 (是否成功, 跳转ID)"""
        
        # 等待匹配
        matched_pos = None
        if step.match_type == MATCH_IMAGE:
            matched_pos = self._wait_for_image(step)
        else:
            matched_pos = step.match_position
            # 如果是等待操作，直接返回成功（延时由 _run_loop 统一处理）
            if step.operation == OP_WAIT:
                return True, None
                
        success = matched_pos is not None
        
        # 执行操作
        if success and step.operation != OP_WAIT:
            click_pos = step.click_position if step.click_position else matched_pos
            dx, dy = ClickEngine._random_offset(step.click_radius)
            
            if step.operation == OP_CLICK:
                pyautogui.click(x=int(click_pos[0]) + dx, y=int(click_pos[1]) + dy, button=step.click_button)
            elif step.operation == OP_DOUBLE_CLICK:
                pyautogui.doubleClick(x=int(click_pos[0]) + dx, y=int(click_pos[1]) + dy, button=step.click_button)
            elif step.operation == OP_MIDDLE_CLICK:
                pyautogui.click(x=int(click_pos[0]) + dx, y=int(click_pos[1]) + dy, button='middle')
            elif step.operation == OP_KEY:
                pyautogui.press(step.key_code)
            elif step.operation == OP_COMBO_KEY:
                pyautogui.hotkey(*step.combo_keys)
            elif step.operation == OP_SCROLL:
                pyautogui.scroll(step.scroll_amount, x=int(click_pos[0]) + dx, y=int(click_pos[1]) + dy)
            elif step.operation == OP_DRAG:
                # 拖动操作
                if step.drag_end:
                    # 确定起点
                    if step.drag_use_match_as_start and matched_pos:
                        start_x, start_y = int(matched_pos[0]), int(matched_pos[1])
                    elif step.drag_start:
                        start_x, start_y = int(step.drag_start[0]), int(step.drag_start[1])
                    else:
                        start_x, start_y = int(click_pos[0]), int(click_pos[1])
                    
                    end_x, end_y = int(step.drag_end[0]), int(step.drag_end[1])
                    
                    # 执行拖动
                    pyautogui.moveTo(start_x, start_y)
                    pyautogui.drag(end_x - start_x, end_y - start_y, 
                                   duration=step.drag_duration, button=step.click_button)
                
        return success, None
        
    def _wait_for_image(self, step: FlowStep) -> Optional[Tuple[int, int]]:
        """等待截图匹配"""
        if step.match_image_data is None:
            return None
            
        start_time = time.time()
        timeout_sec = step.timeout / 1000.0
        
        while time.time() - start_time < timeout_sec:
            if not self._running:
                return None
                
            # 截屏（支持多显示器）
            if step.match_region:
                # 有指定区域：直接截取该区域
                screenshot = pyautogui.screenshot(region=step.match_region)
                offset_x, offset_y = 0, 0
            else:
                # 截取整个虚拟屏幕（所有显示器）
                screenshot, (offset_x, offset_y) = _screenshot_virtual_screen()
                
            # 转为numpy
            screen_np = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            # 模板匹配
            result = cv2.matchTemplate(screen_np, step.match_image_data, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            if max_val >= step.match_threshold:
                # 返回中心点（转换为屏幕坐标）
                h, w = step.match_image_data.shape[:2]
                center_x = max_loc[0] + w // 2 + offset_x
                center_y = max_loc[1] + h // 2 + offset_y
                if step.match_region:
                    center_x += step.match_region[0]
                    center_y += step.match_region[1]
                return (center_x, center_y)
                
            time.sleep(0.1)
            
        return None


# ═══════════════════════════════════════════════════════════════
#  ClickEngine — 基础点击引擎
# ═══════════════════════════════════════════════════════════════
class ClickEngine:
    """管理自动点击的启动、停止与进度回调"""

    def __init__(self):
        self._running = False
        self._lock = threading.Lock()

    @staticmethod
    def _random_offset(radius):
        """在以原点为圆心、radius为半径的圆内均匀随机取一个偏移"""
        if radius <= 0:
            return 0, 0
        angle = random.uniform(0, 2 * math.pi)
        r = radius * math.sqrt(random.random())  # 均匀面积分布
        return int(round(r * math.cos(angle))), int(round(r * math.sin(angle)))

    @property
    def running(self):
        with self._lock:
            return self._running

    def start(self, x, y, count, interval_ms,
              button='left', speed=1.0, radius=0,
              on_progress=None, on_done=None):
        with self._lock:
            if self._running:
                return
            self._running = True

        threading.Thread(
            target=self._loop,
            args=(x, y, count, interval_ms, button, speed, radius,
                  on_progress, on_done),
            daemon=True
        ).start()

    def stop(self):
        with self._lock:
            self._running = False

    def _loop(self, x, y, count, interval_ms, button, speed,
              radius, on_progress, on_done):
        interval = max(interval_ms / 1000.0 / speed, 0.005)
        clicked = 0
        err = None
        try:
            while True:
                with self._lock:
                    if not self._running:
                        break
                if 0 < count <= clicked:
                    break
                dx, dy = self._random_offset(radius)
                pyautogui.click(x=int(x) + dx, y=int(y) + dy, button=button)
                clicked += 1
                if on_progress:
                    try:
                        on_progress(clicked, count)
                    except Exception:
                        pass
                if 0 < count <= clicked:
                    break
                time.sleep(interval)
        except pyautogui.FailSafeException:
            err = "安全退出：鼠标已移至屏幕左上角"
        except Exception as e:
            err = str(e)
        finally:
            with self._lock:
                self._running = False
            if on_done:
                try:
                    on_done(err)
                except Exception:
                    pass


# ═══════════════════════════════════════════════════════════════
#  Recorder — 操作录制器
# ═══════════════════════════════════════════════════════════════
class Recorder:
    """录制点击操作、播放、保存、管理录制文件"""

    def __init__(self, rec_dir=None):
        self.rec_dir = Path(rec_dir) if rec_dir else _APP_DIR / "recordings"
        self.rec_dir.mkdir(parents=True, exist_ok=True)

        self._recording = False
        self._playing   = False
        self._events    = []
        self._t0        = None
        self._ml        = None
        self._on_event  = None

    @property
    def recording(self):
        return self._recording

    @property
    def playing(self):
        return self._playing

    @property
    def events(self):
        return list(self._events)

    def start_recording(self, on_event=None, record_mouse=True,
                             record_key=False, record_drag=True,
                             record_move=False):
        if self._recording:
            return
        self._recording = True
        self._events    = []
        self._t0        = time.time()
        self._on_event  = on_event
        # 记录虚拟屏幕尺寸（支持多显示器坐标）
        vrect = _get_virtual_screen_rect()
        self._rec_vleft, self._rec_vtop = vrect[0], vrect[1]
        self._rec_w, self._rec_h = vrect[2], vrect[3]

        self._drag_state = None
        DRAG_THRESHOLD = 5
        MOVE_INTERVAL = 0.05   # 移动采样间隔（秒）
        self._move_last_t = 0.0
        self._move_last_x = None
        self._move_last_y = None
        self._move_count  = 0

        def _btn_name(button):
            return {
                pynput_mouse.Button.left:   'left',
                pynput_mouse.Button.right:  'right',
                pynput_mouse.Button.middle: 'middle',
            }.get(button, 'left')

        def _emit(ev):
            self._events.append(ev)
            if self._on_event:
                try:
                    self._on_event('add', ev)
                except Exception:
                    pass

        def _on_click(x, y, button, pressed):
            if not self._recording:
                return False
            if not record_mouse:
                return True
            btn = _btn_name(button)
            now = round(time.time() - self._t0, 3)

            if pressed:
                if record_drag:
                    # 在按下时就记录点击事件（而非等待松开），确保时序准确
                    self._drag_state = {
                        'button': btn,
                        'x0': int(x), 'y0': int(y),
                        't0': now,
                        '_emitted': False,
                    }
                    # 立即发出 click 事件（基于 press 位置和时间）
                    ev = {
                        'type': 'click',
                        'x': int(x), 'y': int(y),
                        'button': btn,
                        'time': now,
                        'press_time': now,
                        'release_time': now,   # 初始等于 press_time，松开时更新
                        'hold_duration': 0.0,
                    }
                    _emit(ev)
                    self._drag_state['_emitted'] = True
                else:
                    ev = {
                        'type': 'click',
                        'x': int(x), 'y': int(y),
                        'button': btn,
                        'time': now,
                        'press_time': now,
                        'release_time': now,
                        'hold_duration': 0.0,
                    }
                    _emit(ev)
            else:
                if record_drag and self._drag_state is not None:
                    ds = self._drag_state
                    self._drag_state = None
                    dx = abs(int(x) - ds['x0'])
                    dy = abs(int(y) - ds['y0'])
                    if dx > DRAG_THRESHOLD or dy > DRAG_THRESHOLD:
                        # 是拖动操作：替换之前发出的 click 为 drag
                        if ds['_emitted'] and len(self._events) > 0:
                            self._events.pop()
                            if self._on_event:
                                try:
                                    self._on_event('remove_last', None)
                                except Exception:
                                    pass
                        ev = {
                            'type': 'drag',
                            'x0': ds['x0'], 'y0': ds['y0'],
                            'x1': int(x), 'y1': int(y),
                            'button': ds['button'],
                            'time': ds['t0'],
                            'duration': round(now - ds['t0'], 3),
                        }
                        _emit(ev)
                    else:
                        # 普通点击：更新 release_time 和 hold_duration
                        hold = round(now - ds['t0'], 3)
                        if ds['_emitted'] and len(self._events) > 0:
                            last_ev = self._events[-1]
                            last_ev['release_time'] = now
                            last_ev['hold_duration'] = hold
                else:
                    # 非拖动录制模式下的松开：更新最近一个 click 的 release_time
                    if len(self._events) > 0:
                        last_ev = self._events[-1]
                        if last_ev.get('type') == 'click' and last_ev.get('release_time', 0) == last_ev.get('time', 0):
                            last_ev['release_time'] = now
                            last_ev['hold_duration'] = round(now - last_ev['time'], 3)
            return True

        def _on_move(x, y):
            if not self._recording:
                return
            now = time.time() - self._t0
            if (now - self._move_last_t) < MOVE_INTERVAL:
                return
            px, py = self._move_last_x, self._move_last_y
            if px is not None:
                dx = abs(int(x) - int(px))
                dy = abs(int(y) - int(py))
                if dx < 2 and dy < 2:
                    return
            self._move_last_t = now
            self._move_last_x = x
            self._move_last_y = y
            self._move_count += 1
            if self._move_count <= 2:
                return
            ev = {
                'type': 'move',
                'x': int(x), 'y': int(y),
                'time': round(now, 3),
            }
            _emit(ev)

        if record_move:
            self._ml = pynput_mouse.Listener(on_click=_on_click, on_move=_on_move)
        else:
            self._ml = pynput_mouse.Listener(on_click=_on_click)
        self._ml.start()

        # 键盘录制（追踪修饰键状态，支持组合键）
        self._kl = None
        if record_key:
            _mods_pressed = set()
            _MODIFIER_KEYS = {'Key.ctrl_l', 'Key.ctrl_r', 'Key.shift_l', 'Key.shift_r',
                              'Key.alt_l', 'Key.alt_r', 'Key.cmd', 'Key.cmd_l', 'Key.cmd_r',
                              'Key.alt_gr', 'Key.shift', 'Key.ctrl', 'Key.alt'}
            _key_press_times = {}  # key -> press_time，用于计算按住时长

            def _on_press(key):
                if not self._recording:
                    return False
                try:
                    key_str = key.char
                except AttributeError:
                    key_str = str(key)
                key_name = str(key)
                now = round(time.time() - self._t0, 3)
                if key_name in _MODIFIER_KEYS:
                    _mods_pressed.add(_MODIFIER_UNIFY.get(key_name, key_name))
                    _key_press_times[key_str] = now
                    return True
                # 记录按下时间
                _key_press_times[key_str] = now
                mods_list = sorted(_mods_pressed)
                ev = {
                    'type': 'key',
                    'key': key_str,
                    'mods': mods_list,
                    'time': now,
                    'press_time': now,
                    'release_time': now,
                    'hold_duration': 0.0,
                }
                _emit(ev)
                return True

            def _on_release(key):
                key_name = str(key)
                unified = _MODIFIER_UNIFY.get(key_name, key_name)
                _mods_pressed.discard(unified)
                # 更新最近一个同名按键事件的 release_time 和 hold_duration
                try:
                    key_str = key.char
                except AttributeError:
                    key_str = str(key)
                now = round(time.time() - self._t0, 3)
                press_t = _key_press_times.pop(key_str, None)
                if press_t is not None and self._events:
                    for ev in reversed(self._events):
                        if ev.get('type') == 'key' and ev.get('key') == key_str and ev.get('release_time', 0) == ev.get('time', 0):
                            ev['release_time'] = now
                            ev['hold_duration'] = round(now - press_t, 3)
                            break

            self._kl = pynput_keyboard.Listener(on_press=_on_press, on_release=_on_release)
            self._kl.start()

    def stop_recording(self):
        self._recording = False
        self._drag_state = None
        if self._ml:
            self._ml.stop()
            self._ml = None
        if self._kl:
            self._kl.stop()
            self._kl = None

    def play(self, events=None, speed=1.0, loop=False,
             on_progress=None, on_done=None, rec_resolution=None,
             radius=0):
        if self._playing:
            return
        ev_list = events if events is not None else self._events
        if not ev_list:
            return
        self._playing = True

        # 分辨率自适应缩放（使用虚拟屏幕尺寸，支持多显示器）
        cur_vrect = _get_virtual_screen_rect()
        cur_w, cur_h = cur_vrect[2], cur_vrect[3]
        if rec_resolution:
            rec_w, rec_h = rec_resolution
        else:
            rec_w, rec_h = getattr(self, '_rec_w', cur_w), getattr(self, '_rec_h', cur_h)
        need_scale = (rec_w != cur_w or rec_h != cur_h) and rec_w > 0 and rec_h > 0
        sx = cur_w / rec_w if need_scale else 1.0
        sy = cur_h / rec_h if need_scale else 1.0

        def _run():
            err = None
            # 临时禁用 pyautogui.PAUSE，避免每次调用累积 5ms 延迟
            saved_pause = pyautogui.PAUSE
            pyautogui.PAUSE = 0
            try:
                while self._playing:
                    # 使用绝对时间基准来补偿 sleep 精度误差
                    t_start = time.monotonic()
                    prev = 0
                    for i, ev in enumerate(ev_list):
                        if not self._playing:
                            return
                        # 计算目标延迟
                        target_delay = (ev['time'] - prev) / speed
                        extra_delay = ev.get('_extra_delay', 0)
                        if extra_delay > 0:
                            target_delay += extra_delay / speed
                        prev = ev['time']

                        # 精确等待：先 sleep 整数毫秒，剩余用 busy-wait 补偿
                        if target_delay > 0 and i > 0:
                            elapsed = time.monotonic() - t_start
                            # 基于录制时间戳计算期望的绝对等待时间
                            expected = ev['time'] / speed
                            wait = expected - elapsed
                            if extra_delay > 0:
                                wait += extra_delay / speed
                            if wait > 0.001:
                                time.sleep(wait - 0.001)
                            # busy-wait 精确补偿最后 1ms
                            while (time.monotonic() - t_start) < expected + (extra_delay / speed if extra_delay > 0 else 0):
                                if not self._playing:
                                    return
                                pass

                        if not self._playing:
                            return
                        if ev['type'] == 'click':
                            cx, cy = int(ev['x'] * sx), int(ev['y'] * sy)
                            dx, dy = ClickEngine._random_offset(radius)
                            hold = ev.get('hold_duration', 0)
                            btn = ev.get('button', 'left')
                            if hold > 0.005:
                                # 有按住时长：mouseDown → sleep → mouseUp
                                pyautogui.mouseDown(x=cx + dx, y=cy + dy, button=btn)
                                time.sleep(hold / speed)
                                pyautogui.mouseUp(x=cx + dx, y=cy + dy, button=btn)
                            else:
                                pyautogui.click(x=cx + dx, y=cy + dy, button=btn)
                        elif ev['type'] == 'drag':
                            x0 = int(ev['x0'] * sx)
                            y0 = int(ev['y0'] * sy)
                            x1 = int(ev['x1'] * sx)
                            y1 = int(ev['y1'] * sy)
                            dur = ev.get('duration', 0.5)
                            if dur > 0:
                                pyautogui.moveTo(
                                    x0, y0,
                                    duration=min(dur / speed, 3.0)
                                )
                                pyautogui.drag(
                                    x1 - x0, y1 - y0,
                                    duration=min(dur / speed, 3.0),
                                    button=ev.get('button', 'left')
                                )
                            else:
                                pyautogui.drag(
                                    x1 - x0, y1 - y0,
                                    duration=0.2,
                                    button=ev.get('button', 'left')
                                )
                        elif ev['type'] == 'move':
                            pyautogui.moveTo(
                                int(ev['x'] * sx),
                                int(ev['y'] * sy),
                                duration=0
                            )
                            # 移动后等待 hold_duration（可编辑的额外延迟）
                            move_hold = ev.get('hold_duration', 0)
                            if move_hold > 0:
                                time.sleep(move_hold / speed)
                        elif ev['type'] == 'key':
                            key_str = ev.get('key', '')
                            if key_str:
                                try:
                                    mods = ev.get('mods', [])
                                    if mods:
                                        mod_keys = [_resolve_key(m) for m in mods if _resolve_key(m)]
                                        resolved = _resolve_key(key_str)
                                        if mod_keys and resolved:
                                            pyautogui.hotkey(*mod_keys, resolved)
                                        else:
                                            pyautogui.press(resolved)
                                    else:
                                        pyautogui.press(_resolve_key(key_str))
                                except Exception:
                                    pass
                        if on_progress:
                            try:
                                on_progress(i + 1, len(ev_list))
                            except Exception:
                                pass
                    if not loop:
                        break
            except pyautogui.FailSafeException:
                err = "安全退出：鼠标已移至屏幕左上角"
            except Exception as e:
                err = str(e)
            finally:
                pyautogui.PAUSE = saved_pause
                self._playing = False
                if on_done:
                    try:
                        on_done(err)
                    except Exception:
                        pass

        threading.Thread(target=_run, daemon=True).start()

    def stop_playback(self):
        self._playing = False

    @staticmethod
    def _safe_name(name):
        safe = "".join(c for c in name if c.isalnum() or c in '_- .').strip()
        return safe or "unnamed"

    def save(self, name, events=None):
        ev_list = events if events is not None else self._events
        if not ev_list:
            return None
        name = self._safe_name(name)
        path = self.rec_dir / f"{name}.json"
        rec_w, rec_h = getattr(self, '_rec_w', 0), getattr(self, '_rec_h', 0)
        if rec_w == 0:
            vrect = _get_virtual_screen_rect()
            rec_w, rec_h = vrect[2], vrect[3]
        data = {
            'name':        name,
            'created':     datetime.now().isoformat(),
            'event_count': len(ev_list),
            'duration':    round(ev_list[-1]['time'], 3),
            'resolution':  [rec_w, rec_h],
            'events':      ev_list,
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return str(path)

    def load(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def list_all(self):
        result = []
        for p in sorted(self.rec_dir.glob('*.json'),
                        key=lambda f: f.stat().st_mtime, reverse=True):
            try:
                d = self.load(p)
                result.append({
                    'path':        str(p),
                    'name':        d.get('name', p.stem),
                    'created':     d.get('created', ''),
                    'count':       d.get('event_count', 0),
                    'duration':    d.get('duration', 0),
                    'resolution':  d.get('resolution', None),
                    'events':      d.get('events', []),
                })
            except Exception:
                pass
        return result

    def rename(self, old_path, new_name):
        old = Path(old_path)
        new_name = self._safe_name(new_name)
        new = old.parent / f"{new_name}.json"
        if new.exists() and new != old:
            return False
        old.rename(new)
        try:
            d = self.load(str(new))
            d['name'] = new_name
            with open(new, 'w', encoding='utf-8') as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return str(new)

    def delete(self, path):
        try:
            Path(path).unlink()
            return True
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════
#  StepEditDialog - 步骤编辑对话框
# ═══════════════════════════════════════════════════════════════
class StepEditDialog(tk.Toplevel):
    """步骤详细编辑对话框"""
    
    def __init__(self, parent, step: FlowStep, project: FlowProject, 
                 on_capture_region: Callable = None):
        super().__init__(parent)
        self.step = step
        self.project = project
        self.on_capture_region = on_capture_region
        self.result = False
        
        self.title(f"编辑步骤 - {step.id}")
        self.geometry("520x680")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        
        self._build_ui()
        self._load_values()
        
        # 居中
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        
    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 匹配设置页
        match_frame = ttk.Frame(notebook, padding=10)
        notebook.add(match_frame, text=" 匹配设置 ")
        self._build_match_tab(match_frame)
        
        # 操作设置页
        op_frame = ttk.Frame(notebook, padding=10)
        notebook.add(op_frame, text=" 操作设置 ")
        self._build_operation_tab(op_frame)
        
        # 分支设置页
        branch_frame = ttk.Frame(notebook, padding=10)
        notebook.add(branch_frame, text=" 分支设置 ")
        self._build_branch_tab(branch_frame)
        
        # 底部按钮
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill='x', padx=10, pady=10)
        ttk.Button(btn_frame, text="确定", command=self._on_ok, width=12).pack(side='right', padx=4)
        ttk.Button(btn_frame, text="取消", command=self._on_cancel, width=12).pack(side='right')
        
    def _build_match_tab(self, parent):
        # 描述
        f = ttk.Frame(parent)
        f.pack(fill='x', pady=4)
        ttk.Label(f, text="步骤描述:", width=12, anchor='e').pack(side='left')
        self.var_desc = tk.StringVar()
        ttk.Entry(f, textvariable=self.var_desc, width=40).pack(side='left', fill='x', expand=True)
        
        # 匹配方式
        f = ttk.LabelFrame(parent, text="匹配方式", padding=8)
        f.pack(fill='x', pady=8)
        
        self.var_match_type = tk.StringVar(value=MATCH_POSITION)
        ttk.Radiobutton(f, text="精确坐标", variable=self.var_match_type, 
                        value=MATCH_POSITION, command=self._on_match_type_change).pack(anchor='w')
        ttk.Radiobutton(f, text="截图匹配", variable=self.var_match_type, 
                        value=MATCH_IMAGE, command=self._on_match_type_change).pack(anchor='w')
        
        # 坐标设置
        self.pos_frame = ttk.LabelFrame(parent, text="坐标位置", padding=8)
        self.pos_frame.pack(fill='x', pady=4)
        
        fp = ttk.Frame(self.pos_frame)
        fp.pack(fill='x')
        ttk.Label(fp, text="X:").pack(side='left')
        self.var_pos_x = tk.IntVar(value=0)
        ttk.Spinbox(fp, from_=0, to=9999, textvariable=self.var_pos_x, width=8).pack(side='left', padx=(0, 12))
        ttk.Label(fp, text="Y:").pack(side='left')
        self.var_pos_y = tk.IntVar(value=0)
        ttk.Spinbox(fp, from_=0, to=9999, textvariable=self.var_pos_y, width=8).pack(side='left', padx=(0, 12))
        ttk.Button(fp, text="📍 取点", command=self._pick_position, width=8).pack(side='left')
        
        # 截图设置
        self.img_frame = ttk.LabelFrame(parent, text="截图模板", padding=8)
        self.img_frame.pack(fill='x', pady=4)
        
        fi = ttk.Frame(self.img_frame)
        fi.pack(fill='x')
        self.var_img_path = tk.StringVar(value="未选择")
        ttk.Label(fi, textvariable=self.var_img_path, width=30).pack(side='left')
        ttk.Button(fi, text="框选截图", command=self._capture_region, width=10).pack(side='left', padx=4)
        
        # 预览
        self.preview_frame = ttk.Frame(self.img_frame)
        self.preview_frame.pack(fill='x', pady=4)
        self.img_preview_label = ttk.Label(self.preview_frame, text="无截图")
        self.img_preview_label.pack()
        
        # 匹配设置
        f = ttk.LabelFrame(parent, text="匹配参数", padding=8)
        f.pack(fill='x', pady=4)
        
        fp1 = ttk.Frame(f)
        fp1.pack(fill='x', pady=2)
        ttk.Label(fp1, text="匹配阈值:", width=10, anchor='e').pack(side='left')
        self.var_threshold = tk.DoubleVar(value=0.8)
        ttk.Scale(fp1, from_=0.1, to=1.0, variable=self.var_threshold, 
                  orient='horizontal', length=200).pack(side='left')
        self.lbl_threshold = ttk.Label(fp1, text="80%", width=6)
        self.lbl_threshold.pack(side='left')
        self.var_threshold.trace_add('write', lambda *_: self.lbl_threshold.config(
            text=f"{int(self.var_threshold.get() * 100)}%"
        ))
        
        fp2 = ttk.Frame(f)
        fp2.pack(fill='x', pady=2)
        ttk.Label(fp2, text="匹配范围:", width=10, anchor='e').pack(side='left')
        self.var_scope = tk.StringVar(value=SCOPE_FULLSCREEN)
        ttk.Combobox(fp2, textvariable=self.var_scope, values=[
            SCOPE_FULLSCREEN, SCOPE_SINGLE_SCREEN
        ], width=15, state='readonly').pack(side='left')
        
        fp3 = ttk.Frame(f)
        fp3.pack(fill='x', pady=2)
        ttk.Label(fp3, text="超时时间:", width=10, anchor='e').pack(side='left')
        self.var_timeout = tk.IntVar(value=10000)
        ttk.Spinbox(fp3, from_=100, to=60000, textvariable=self.var_timeout, 
                    width=10, increment=1000).pack(side='left')
        ttk.Label(fp3, text="毫秒").pack(side='left')
        
        # 初始化显示
        self._on_match_type_change()
        
    def _build_operation_tab(self, parent):
        # 操作类型
        f = ttk.LabelFrame(parent, text="操作类型", padding=8)
        f.pack(fill='x', pady=4)
        
        self.var_operation = tk.StringVar(value=OP_CLICK)
        op_types = [OP_CLICK, OP_DOUBLE_CLICK, OP_KEY, OP_COMBO_KEY, OP_SCROLL, OP_MIDDLE_CLICK, OP_WAIT, OP_DRAG]
        for i, op in enumerate(op_types):
            ttk.Radiobutton(f, text=OP_NAMES[op], variable=self.var_operation,
                           value=op, command=self._on_operation_change).grid(
                               row=i//3, column=i%3, sticky='w', padx=8, pady=2)
        
        # 点击位置
        self.click_frame = ttk.LabelFrame(parent, text="点击位置", padding=8)
        self.click_frame.pack(fill='x', pady=4)
        
        self.var_click_use_match = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.click_frame, text="使用匹配位置", 
                        variable=self.var_click_use_match,
                        command=self._on_click_mode_change).pack(anchor='w')
        
        self.click_pos_frame = ttk.Frame(self.click_frame)
        self.click_pos_frame.pack(fill='x', pady=4)
        ttk.Label(self.click_pos_frame, text="X:").pack(side='left')
        self.var_click_x = tk.IntVar(value=0)
        ttk.Spinbox(self.click_pos_frame, from_=0, to=9999, 
                    textvariable=self.var_click_x, width=8).pack(side='left', padx=(0, 12))
        ttk.Label(self.click_pos_frame, text="Y:").pack(side='left')
        self.var_click_y = tk.IntVar(value=0)
        ttk.Spinbox(self.click_pos_frame, from_=0, to=9999, 
                    textvariable=self.var_click_y, width=8).pack(side='left')
        
        # 点击按钮
        self.btn_frame = ttk.LabelFrame(parent, text="鼠标按键", padding=8)
        self.btn_frame.pack(fill='x', pady=4)
        
        self.var_click_button = tk.StringVar(value='left')
        for txt, val in [("左键", "left"), ("右键", "right")]:
            ttk.Radiobutton(self.btn_frame, text=txt, variable=self.var_click_button,
                           value=val).pack(side='left', padx=12)

        # 容错范围
        self.radius_frame = ttk.LabelFrame(parent, text="容错范围", padding=8)
        self.radius_frame.pack(fill='x', pady=4)

        fr = ttk.Frame(self.radius_frame)
        fr.pack(fill='x')
        ttk.Label(fr, text="随机偏移半径:").pack(side='left')
        self.var_click_radius = tk.IntVar(value=0)
        self.spb_click_radius = ttk.Spinbox(fr, from_=0, to=30, textvariable=self.var_click_radius,
                     width=5, command=lambda: self._on_radius_change(
                         self.var_click_radius, self.canvas_radius_preview))
        self.spb_click_radius.pack(side='left', padx=4)
        self.scale_click_radius = ttk.Scale(fr, from_=0, to=30, variable=self.var_click_radius,
                                             orient='horizontal', length=120,
                                             command=lambda v: self._on_radius_change(
                                                 self.var_click_radius, self.canvas_radius_preview))
        self.scale_click_radius.pack(side='left', padx=4)
        ttk.Label(fr, text="(0~30)",
                  foreground='gray').pack(side='left')
        # 圆圈预览
        self.canvas_radius_preview = tk.Canvas(fr, width=64, height=64,
                                                bg='white', highlightthickness=1,
                                                highlightbackground='#CCCCCC')
        self.canvas_radius_preview.pack(side='right', padx=8)
        self.canvas_radius_preview.update_idletasks()
        self._draw_radius_circle(self.canvas_radius_preview, 0)

        # 按键设置
        self.key_frame = ttk.LabelFrame(parent, text="按键设置", padding=8)
        self.key_frame.pack(fill='x', pady=4)
        
        fkk = ttk.Frame(self.key_frame)
        fkk.pack(fill='x')
        ttk.Label(fkk, text="按键:").pack(side='left')
        self.var_key = tk.StringVar()
        ttk.Entry(fkk, textvariable=self.var_key, width=15).pack(side='left', padx=4)
        ttk.Label(fkk, text="(如: a, enter, space, f1)", foreground='gray').pack(side='left')
        
        # 组合键设置
        self.combo_frame = ttk.LabelFrame(parent, text="组合键设置", padding=8)
        self.combo_frame.pack(fill='x', pady=4)
        
        ttk.Label(self.combo_frame, text="按键列表 (用逗号分隔):").pack(anchor='w')
        self.var_combo_keys = tk.StringVar()
        ttk.Entry(self.combo_frame, textvariable=self.var_combo_keys, width=40).pack(fill='x', pady=4)
        ttk.Label(self.combo_frame, text="示例: ctrl,shift,a 或 alt,f4", foreground='gray').pack(anchor='w')
        
        # 滚轮设置
        self.scroll_frame = ttk.LabelFrame(parent, text="滚轮设置", padding=8)
        self.scroll_frame.pack(fill='x', pady=4)
        
        fsc = ttk.Frame(self.scroll_frame)
        fsc.pack(fill='x')
        ttk.Label(fsc, text="滚动量:").pack(side='left')
        self.var_scroll = tk.IntVar(value=100)
        ttk.Spinbox(fsc, from_=-1000, to=1000, textvariable=self.var_scroll, 
                    width=10, increment=50).pack(side='left')
        ttk.Label(fsc, text="(正数向上，负数向下)", foreground='gray').pack(side='left')
        
        # 拖动设置
        self.drag_frame = ttk.LabelFrame(parent, text="拖动设置", padding=8)
        self.drag_frame.pack(fill='x', pady=4)
        
        # 使用匹配位置作为起点
        self.var_drag_use_match = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.drag_frame, text="使用匹配位置作为起点", 
                        variable=self.var_drag_use_match,
                        command=self._on_drag_mode_change).pack(anchor='w')
        
        # 拖动起点
        self.drag_start_frame = ttk.Frame(self.drag_frame)
        self.drag_start_frame.pack(fill='x', pady=4)
        ttk.Label(self.drag_start_frame, text="起点 X:").pack(side='left')
        self.var_drag_start_x = tk.IntVar(value=0)
        ttk.Spinbox(self.drag_start_frame, from_=0, to=9999, 
                    textvariable=self.var_drag_start_x, width=8).pack(side='left', padx=(0, 8))
        ttk.Label(self.drag_start_frame, text="Y:").pack(side='left')
        self.var_drag_start_y = tk.IntVar(value=0)
        ttk.Spinbox(self.drag_start_frame, from_=0, to=9999, 
                    textvariable=self.var_drag_start_y, width=8).pack(side='left', padx=(0, 8))
        ttk.Button(self.drag_start_frame, text="取点", 
                   command=self._pick_drag_start, width=6).pack(side='left')
        
        # 拖动终点
        fdg2 = ttk.Frame(self.drag_frame)
        fdg2.pack(fill='x', pady=4)
        ttk.Label(fdg2, text="终点 X:").pack(side='left')
        self.var_drag_end_x = tk.IntVar(value=0)
        ttk.Spinbox(fdg2, from_=0, to=9999, 
                    textvariable=self.var_drag_end_x, width=8).pack(side='left', padx=(0, 8))
        ttk.Label(fdg2, text="Y:").pack(side='left')
        self.var_drag_end_y = tk.IntVar(value=0)
        ttk.Spinbox(fdg2, from_=0, to=9999, 
                    textvariable=self.var_drag_end_y, width=8).pack(side='left', padx=(0, 8))
        ttk.Button(fdg2, text="取点", 
                   command=self._pick_drag_end, width=6).pack(side='left')
        
        # 拖动持续时间
        fdg3 = ttk.Frame(self.drag_frame)
        fdg3.pack(fill='x', pady=4)
        ttk.Label(fdg3, text="持续时间:").pack(side='left')
        self.var_drag_duration = tk.DoubleVar(value=0.5)
        ttk.Spinbox(fdg3, from_=0.1, to=10.0, textvariable=self.var_drag_duration, 
                    width=8, increment=0.1).pack(side='left')
        ttk.Label(fdg3, text="秒").pack(side='left')
        
        # 延时
        self.delay_frame = ttk.LabelFrame(parent, text="延时", padding=8)
        self.delay_frame.pack(fill='x', pady=4)
        
        fd = ttk.Frame(self.delay_frame)
        fd.pack(fill='x')
        ttk.Label(fd, text="步骤后延时:", width=12, anchor='e').pack(side='left')
        self.var_delay = tk.IntVar(value=100)
        ttk.Spinbox(fd, from_=0, to=60000, textvariable=self.var_delay, 
                    width=10, increment=100).pack(side='left')
        ttk.Label(fd, text="毫秒").pack(side='left')
        
        # 初始化
        self._on_operation_change()
        self._on_click_mode_change()
        
    def _build_branch_tab(self, parent):
        # 启用分支
        self.var_branch_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(parent, text="启用分支逻辑", variable=self.var_branch_enabled,
                        command=self._on_branch_change).pack(anchor='w', pady=8)
        
        # 分支类型选择
        self.branch_type_frame = ttk.LabelFrame(parent, text="分支类型", padding=8)
        self.branch_type_frame.pack(fill='x', pady=4)
        
        self.var_branch_type = tk.StringVar(value='condition')
        ttk.Radiobutton(self.branch_type_frame, text="条件跳转 - 根据匹配成功/失败跳转到不同步骤",
                        variable=self.var_branch_type, value='condition',
                        command=self._on_branch_type_change).pack(anchor='w', pady=2)
        ttk.Radiobutton(self.branch_type_frame, text="无条件跳转 - 始终跳转到指定步骤",
                        variable=self.var_branch_type, value='always',
                        command=self._on_branch_type_change).pack(anchor='w', pady=2)
        
        # 条件跳转设置
        self.branch_condition_frame = ttk.LabelFrame(parent, text="条件跳转", padding=8)
        self.branch_condition_frame.pack(fill='x', pady=4)
        
        # 匹配成功跳转
        f1 = ttk.Frame(self.branch_condition_frame)
        f1.pack(fill='x', pady=4)
        ttk.Label(f1, text="匹配成功 →", width=12, anchor='e').pack(side='left')
        self.var_branch_match = tk.StringVar()
        self.cb_match = ttk.Combobox(f1, textvariable=self.var_branch_match, width=30, state='readonly')
        self.cb_match.pack(side='left', fill='x', expand=True)
        
        # 未匹配跳转
        f2 = ttk.Frame(self.branch_condition_frame)
        f2.pack(fill='x', pady=4)
        ttk.Label(f2, text="未匹配 →", width=12, anchor='e').pack(side='left')
        self.var_branch_nomatch = tk.StringVar()
        self.cb_nomatch = ttk.Combobox(f2, textvariable=self.var_branch_nomatch, width=30, state='readonly')
        self.cb_nomatch.pack(side='left', fill='x', expand=True)
        
        # 无条件跳转设置
        self.branch_always_frame = ttk.LabelFrame(parent, text="无条件跳转", padding=8)
        self.branch_always_frame.pack(fill='x', pady=4)
        
        f3 = ttk.Frame(self.branch_always_frame)
        f3.pack(fill='x', pady=4)
        ttk.Label(f3, text="跳转到 →", width=12, anchor='e').pack(side='left')
        self.var_branch_always = tk.StringVar()
        self.cb_always = ttk.Combobox(f3, textvariable=self.var_branch_always, width=30, state='readonly')
        self.cb_always.pack(side='left', fill='x', expand=True)
        
        # 说明
        ttk.Label(parent, text="提示: 选择「下一步」将按主线顺序执行", 
                  foreground='gray').pack(anchor='w', pady=8)
        
        self._update_branch_options()
        self._on_branch_change()
        self._on_branch_type_change()
        
    def _update_branch_options(self):
        """更新分支下拉选项"""
        options = ['(下一步)']  # 默认选项
        for sid in self.project.mainline_order:
            step = self.project.get_step(sid)
            if step:
                desc = step.description or step.id
                options.append(f"{sid}: {desc[:20]}")
        self.cb_match['values'] = options
        self.cb_nomatch['values'] = options
        self.cb_always['values'] = options
        
    def _on_branch_type_change(self):
        """分支类型变化时切换显示"""
        branch_type = self.var_branch_type.get()
        if branch_type == 'condition':
            self.branch_condition_frame.pack(fill='x', pady=4, before=self.branch_always_frame)
            self.branch_always_frame.pack_forget()
        else:
            self.branch_always_frame.pack(fill='x', pady=4, before=self.branch_condition_frame)
            self.branch_condition_frame.pack_forget()
        
    def _load_values(self):
        """加载步骤值"""
        s = self.step
        self.var_desc.set(s.description)
        self.var_match_type.set(s.match_type)
        self.var_pos_x.set(s.match_position[0])
        self.var_pos_y.set(s.match_position[1])
        if s.match_image_path:
            self.var_img_path.set(s.match_image_path)
        self.var_threshold.set(s.match_threshold)
        self.var_scope.set(s.match_scope)
        self.var_timeout.set(s.timeout)
        
        self.var_operation.set(s.operation)
        self.var_click_use_match.set(s.click_position is None)
        if s.click_position:
            self.var_click_x.set(s.click_position[0])
            self.var_click_y.set(s.click_position[1])
        self.var_click_button.set(s.click_button)
        self.var_click_radius.set(s.click_radius)
        self.var_key.set(s.key_code)
        self.var_combo_keys.set(','.join(s.combo_keys))
        self.var_scroll.set(s.scroll_amount)
        self.var_delay.set(s.delay_after)
        
        # 拖动设置
        self.var_drag_use_match.set(s.drag_use_match_as_start)
        if s.drag_start:
            self.var_drag_start_x.set(s.drag_start[0])
            self.var_drag_start_y.set(s.drag_start[1])
        if s.drag_end:
            self.var_drag_end_x.set(s.drag_end[0])
            self.var_drag_end_y.set(s.drag_end[1])
        self.var_drag_duration.set(s.drag_duration)
        
        self.var_branch_enabled.set(s.branch_enabled)
        self.var_branch_type.set(s.branch_type)
        if s.branch_match_next:
            step = self.project.get_step(s.branch_match_next)
            if step:
                self.var_branch_match.set(f"{s.branch_match_next}: {step.description[:20] or s.branch_match_next}")
        if s.branch_nomatch_next:
            step = self.project.get_step(s.branch_nomatch_next)
            if step:
                self.var_branch_nomatch.set(f"{s.branch_nomatch_next}: {step.description[:20] or s.branch_nomatch_next}")
        if s.branch_always_next:
            step = self.project.get_step(s.branch_always_next)
            if step:
                self.var_branch_always.set(f"{s.branch_always_next}: {step.description[:20] or s.branch_always_next}")
                
        # 更新预览
        if s.match_image_data is not None:
            self._update_image_preview()
            
        self._on_match_type_change()
        self._on_operation_change()
        self._on_click_mode_change()
        self._on_drag_mode_change()
        self._on_branch_change()
        self._on_branch_type_change()
        
    def _on_match_type_change(self):
        is_pos = self.var_match_type.get() == MATCH_POSITION
        state = 'normal' if is_pos else 'disabled'
        for w in self.pos_frame.winfo_children():
            if isinstance(w, ttk.Frame):
                for child in w.winfo_children():
                    try:
                        child.configure(state=state)
                    except:
                        pass
        state = 'normal' if not is_pos else 'disabled'
        for w in self.img_frame.winfo_children():
            if isinstance(w, ttk.Frame):
                for child in w.winfo_children():
                    try:
                        child.configure(state=state)
                    except:
                        pass
                        
    def _on_operation_change(self):
        op = self.var_operation.get()
        # 显示/隐藏相关设置
        show_click = op in [OP_CLICK, OP_DOUBLE_CLICK]
        show_btn = op in [OP_CLICK, OP_DOUBLE_CLICK, OP_DRAG]
        show_key = op == OP_KEY
        show_combo = op == OP_COMBO_KEY
        show_scroll = op == OP_SCROLL
        show_drag = op == OP_DRAG
        show_radius = op in [OP_CLICK, OP_DOUBLE_CLICK, OP_MIDDLE_CLICK]
        
        self.click_frame.pack_forget()
        self.btn_frame.pack_forget()
        self.key_frame.pack_forget()
        self.combo_frame.pack_forget()
        self.scroll_frame.pack_forget()
        self.drag_frame.pack_forget()
        self.radius_frame.pack_forget()
        
        # 重新pack到延时之前（使用命名引用，避免依赖 winfo_children 顺序）
        if show_click:
            self.click_frame.pack(fill='x', pady=4, before=self.delay_frame)
        if show_btn:
            self.btn_frame.pack(fill='x', pady=4, before=self.delay_frame)
        if show_radius:
            self.radius_frame.pack(fill='x', pady=4, before=self.delay_frame)
        if show_key:
            self.key_frame.pack(fill='x', pady=4, before=self.delay_frame)
        if show_combo:
            self.combo_frame.pack(fill='x', pady=4, before=self.delay_frame)
        if show_scroll:
            self.scroll_frame.pack(fill='x', pady=4, before=self.delay_frame)
        if show_drag:
            self.drag_frame.pack(fill='x', pady=4, before=self.delay_frame)
            
    def _on_click_mode_change(self):
        use_match = self.var_click_use_match.get()
        state = 'disabled' if use_match else 'normal'
        for w in self.click_pos_frame.winfo_children():
            try:
                w.configure(state=state)
            except:
                pass
                
    def _on_drag_mode_change(self):
        use_match = self.var_drag_use_match.get()
        state = 'disabled' if use_match else 'normal'
        for w in self.drag_start_frame.winfo_children():
            try:
                w.configure(state=state)
            except:
                pass
                
    def _on_branch_change(self):
        enabled = self.var_branch_enabled.get()
        state = 'normal' if enabled else 'disabled'
        for frame in [self.branch_type_frame, self.branch_condition_frame, self.branch_always_frame]:
            for w in frame.winfo_children():
                if isinstance(w, ttk.Frame):
                    for child in w.winfo_children():
                        try:
                            child.configure(state=state)
                        except:
                            pass
                elif isinstance(w, ttk.Radiobutton):
                    try:
                        w.configure(state=state)
                    except:
                        pass
                        
    def _pick_position(self):
        """取点 - 使用全屏透明窗口方式"""
        # 释放模态抓取，否则 pick_win 无法接收事件
        self.grab_release()
        self.iconify()
        time.sleep(0.3)
        
        # 创建覆盖所有显示器的全屏透明窗口
        pick_win, canvas, (ox, oy) = _create_fullscreen_window(self.master, alpha=0.01)
        pick_win.configure(cursor='cross')
        
        # 提示标签（显示在主显示器顶部中央）
        pri_w, pri_h = _get_primary_screen_size()
        label = tk.Label(pick_win, text="点击屏幕任意位置获取坐标 (Esc取消)", 
                        fg='white', bg='black', font=('Arial', 14))
        label.place(x=pri_w//2, y=30, anchor='center')
        
        def on_click(event):
            x, y = event.x_root, event.y_root
            self.var_pos_x.set(x)
            self.var_pos_y.set(y)
            pick_win.destroy()
            self.deiconify()
            self.grab_set()
            
        def on_escape(event):
            pick_win.destroy()
            self.deiconify()
            self.grab_set()
        
        pick_win.bind('<Button-1>', on_click)
        pick_win.bind('<Escape>', on_escape)
        pick_win.focus_set()
        
    def _finish_pick(self, x, y):
        self.var_pos_x.set(x)
        self.var_pos_y.set(y)
        self.deiconify()
        self.grab_set()
        if hasattr(self, '_pick_listener'):
            self._pick_listener.stop()
            
    def _pick_drag_start(self):
        """取拖动起点 - 使用全屏透明窗口方式"""
        self.grab_release()
        self.iconify()
        time.sleep(0.3)
        
        pick_win, canvas, (ox, oy) = _create_fullscreen_window(self.master, alpha=0.01)
        pick_win.configure(cursor='cross')
        
        pri_w, pri_h = _get_primary_screen_size()
        label = tk.Label(pick_win, text="点击选择拖动起点 (Esc取消)", 
                        fg='white', bg='black', font=('Arial', 14))
        label.place(x=pri_w//2, y=30, anchor='center')
        
        def on_click(event):
            x, y = event.x_root, event.y_root
            self.var_drag_start_x.set(x)
            self.var_drag_start_y.set(y)
            pick_win.destroy()
            self.deiconify()
            self.grab_set()
            
        def on_escape(event):
            pick_win.destroy()
            self.deiconify()
            self.grab_set()
        
        pick_win.bind('<Button-1>', on_click)
        pick_win.bind('<Escape>', on_escape)
        pick_win.focus_set()
        
    def _finish_pick_drag_start(self, x, y):
        self.var_drag_start_x.set(x)
        self.var_drag_start_y.set(y)
        self.deiconify()
        self.grab_set()
        if hasattr(self, '_pick_start_listener'):
            self._pick_start_listener.stop()
            
    def _pick_drag_end(self):
        """取拖动终点 - 使用全屏透明窗口方式"""
        self.grab_release()
        self.iconify()
        time.sleep(0.3)
        
        pick_win, canvas, (ox, oy) = _create_fullscreen_window(self.master, alpha=0.01)
        pick_win.configure(cursor='cross')
        
        pri_w, pri_h = _get_primary_screen_size()
        label = tk.Label(pick_win, text="点击选择拖动终点 (Esc取消)", 
                        fg='white', bg='black', font=('Arial', 14))
        label.place(x=pri_w//2, y=30, anchor='center')
        
        def on_click(event):
            x, y = event.x_root, event.y_root
            self.var_drag_end_x.set(x)
            self.var_drag_end_y.set(y)
            pick_win.destroy()
            self.deiconify()
            self.grab_set()
            
        def on_escape(event):
            pick_win.destroy()
            self.deiconify()
            self.grab_set()
        
        pick_win.bind('<Button-1>', on_click)
        pick_win.bind('<Escape>', on_escape)
        pick_win.focus_set()
            
    def _capture_region(self):
        """框选截图"""
        self.grab_release()
        self.iconify()
        time.sleep(0.3)
        
        # 创建覆盖所有显示器的全屏半透明窗口
        capture_win, canvas, (ox, oy) = _create_fullscreen_window(self.master, alpha=0.3)
        capture_win.configure(cursor='cross')
        
        pri_w, pri_h = _get_primary_screen_size()
        
        # 提示文字
        canvas.create_text(pri_w//2, 30, text="按住鼠标左键框选区域，松开完成截图 (Esc取消)",
                          fill='white', font=('Arial', 14))
        
        self._capture_start = None
        self._capture_rect = None
        
        def on_mouse_down(event):
            # 转换为画布坐标（canvas 原点在虚拟屏幕左上角）
            cx = event.x_root - ox
            cy = event.y_root - oy
            self._capture_start = (event.x_root, event.y_root)
            self._capture_canvas_start = (cx, cy)
            
        def on_mouse_move(event):
            if self._capture_start:
                if self._capture_rect:
                    canvas.delete(self._capture_rect)
                cx = event.x_root - ox
                cy = event.y_root - oy
                sx, sy = self._capture_canvas_start
                self._capture_rect = canvas.create_rectangle(
                    sx, sy, cx, cy,
                    outline='red', width=2, fill=''
                )
                
        def on_mouse_up(event):
            if self._capture_start:
                x1, y1 = self._capture_start
                x2, y2 = event.x_root, event.y_root
                left, right = min(x1, x2), max(x1, x2)
                top, bottom = min(y1, y2), max(y1, y2)
                
                if right - left > 5 and bottom - top > 5:
                    capture_win.destroy()
                    self._do_capture(left, top, right - left, bottom - top)
                else:
                    capture_win.destroy()
                    self.deiconify()
                    
        def on_escape(event):
            capture_win.destroy()
            self.deiconify()
            self.grab_set()
        canvas.bind('<B1-Motion>', on_mouse_move)
        canvas.bind('<ButtonRelease-1>', on_mouse_up)
        capture_win.bind('<Escape>', on_escape)
        
    def _do_capture(self, x, y, w, h):
        """执行截图"""
        try:
            img = pyautogui.screenshot(region=(x, y, w, h))
            img_np = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            
            self.step.match_image_data = img_np
            self.step.match_region = (x, y, w, h)
            self.var_img_path.set(f"区域 ({x},{y},{w},{h})")
            
            self._update_image_preview()
        except Exception as e:
            messagebox.showerror("错误", f"截图失败: {e}")
            
        self.deiconify()
        self.grab_set()
        
    def _update_image_preview(self):
        """更新图片预览"""
        if self.step.match_image_data is not None:
            # 缩放显示
            h, w = self.step.match_image_data.shape[:2]
            max_size = 150
            scale = min(max_size / w, max_size / h)
            new_w, new_h = int(w * scale), int(h * scale)
            
            img_resized = cv2.resize(self.step.match_image_data, (new_w, new_h))
            img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(img_rgb)
            img_tk = ImageTk.PhotoImage(img_pil)
            
            self.img_preview_label.configure(image=img_tk, text='')
            self.img_preview_label.image = img_tk
        else:
            self.img_preview_label.configure(image='', text='无截图')
            
    def _on_ok(self):
        """确定"""
        s = self.step
        s.description = self.var_desc.get()
        s.match_type = self.var_match_type.get()
        s.match_position = (self.var_pos_x.get(), self.var_pos_y.get())
        s.match_threshold = self.var_threshold.get()
        s.match_scope = self.var_scope.get()
        s.timeout = self.var_timeout.get()
        
        s.operation = self.var_operation.get()
        if self.var_click_use_match.get():
            s.click_position = None
        else:
            s.click_position = (self.var_click_x.get(), self.var_click_y.get())
        s.click_button = self.var_click_button.get()
        s.click_radius = self.var_click_radius.get()
        s.key_code = self.var_key.get()
        s.combo_keys = [k.strip() for k in self.var_combo_keys.get().split(',') if k.strip()]
        s.scroll_amount = self.var_scroll.get()
        s.delay_after = self.var_delay.get()
        
        # 拖动设置
        s.drag_use_match_as_start = self.var_drag_use_match.get()
        s.drag_start = (self.var_drag_start_x.get(), self.var_drag_start_y.get())
        s.drag_end = (self.var_drag_end_x.get(), self.var_drag_end_y.get())
        s.drag_duration = self.var_drag_duration.get()
        
        s.branch_enabled = self.var_branch_enabled.get()
        s.branch_type = self.var_branch_type.get()
        # 解析分支跳转
        match_val = self.var_branch_match.get()
        if match_val and ':' in match_val:
            s.branch_match_next = match_val.split(':')[0]
        else:
            s.branch_match_next = None
        nomatch_val = self.var_branch_nomatch.get()
        if nomatch_val and ':' in nomatch_val:
            s.branch_nomatch_next = nomatch_val.split(':')[0]
        else:
            s.branch_nomatch_next = None
        always_val = self.var_branch_always.get()
        if always_val and ':' in always_val:
            s.branch_always_next = always_val.split(':')[0]
        else:
            s.branch_always_next = None
            
        self.result = True
        self.destroy()
        
    def _on_cancel(self):
        self.result = False
        self.destroy()


# ═══════════════════════════════════════════════════════════════
#  FlowCanvas - 流程图画布
# ═══════════════════════════════════════════════════════════════
class FlowCanvas(tk.Canvas):
    """流程图可视化画布"""
    
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, **kwargs)
        self.app = app
        self.project: FlowProject = None
        
        self.selected_nodes: List[str] = []
        self.dragging = False
        self.drag_start = None
        self.drag_node = None
        
        # 连线绘制
        self.drawing_connection = False
        self.connection_start = None
        self.connection_type = None  # 'match' or 'nomatch'
        self.temp_line = None
        
        # 框选
        self.box_selecting = False
        self.box_start = None
        self.box_rect = None
        
        self._bind_events()
        
    def _bind_events(self):
        self.bind('<Button-1>', self._on_click)
        self.bind('<B1-Motion>', self._on_drag)
        self.bind('<ButtonRelease-1>', self._on_release)
        self.bind('<Button-3>', self._on_right_click)
        self.bind('<Control-Button-1>', self._on_ctrl_click)
        self.bind('<Double-Button-1>', self._on_double_click)
        self.bind('<Delete>', self._on_delete)
        
    def set_project(self, project: FlowProject):
        self.project = project
        self.redraw()
        
    def redraw(self):
        """重绘画布"""
        self.delete('all')
        if not self.project:
            return
            
        # 绘制连线
        for step in self.project.steps.values():
            if step.branch_enabled:
                if step.branch_match_next:
                    self._draw_connection(step.id, step.branch_match_next, 'match')
                if step.branch_nomatch_next:
                    self._draw_connection(step.id, step.branch_nomatch_next, 'nomatch')
                    
        # 绘制主线连接
        for i in range(len(self.project.mainline_order) - 1):
            self._draw_connection(
                self.project.mainline_order[i],
                self.project.mainline_order[i + 1],
                'mainline'
            )
            
        # 绘制节点
        for step in self.project.steps.values():
            self._draw_node(step)
            
    def _draw_node(self, step: FlowStep):
        """绘制节点"""
        x, y = step.canvas_x, step.canvas_y
        w, h = NODE_WIDTH, NODE_HEIGHT
        
        # 确定颜色
        if step.id in self.selected_nodes:
            fill_color = NODE_COLORS['selected']
        elif step.id == self.app.flow_engine.current_step_id:
            fill_color = NODE_COLORS['active']
        elif step.is_mainline:
            fill_color = NODE_COLORS['normal']
        elif not self._is_connected(step.id):
            fill_color = NODE_COLORS['disconnected']
        else:
            fill_color = NODE_COLORS['branch']
            
        # 绘制矩形
        tags = ('node', f'node_{step.id}')
        self.create_rectangle(x, y, x + w, y + h, fill=fill_color, 
                             outline='#666', width=2, tags=tags)
        
        # 绘制标题
        title = step.description or step.id
        if len(title) > 15:
            title = title[:15] + '...'
        self.create_text(x + w/2, y + 15, text=title, font=('Arial', 9, 'bold'),
                        tags=tags)
        
        # 绘制操作类型
        op_text = OP_NAMES.get(step.operation, step.operation)
        self.create_text(x + w/2, y + 35, text=f"操作: {op_text}",
                        font=('Arial', 8), fill='#555', tags=tags)
        
        # 绘制匹配方式
        match_text = "坐标" if step.match_type == MATCH_POSITION else "截图"
        self.create_text(x + w/2, y + 50, text=f"匹配: {match_text}",
                        font=('Arial', 8), fill='#555', tags=tags)
        
        # 绘制延时
        self.create_text(x + w/2, y + 65, text=f"延时: {step.delay_after}ms",
                        font=('Arial', 8), fill='#555', tags=tags)
        
        # 分支指示
        if step.branch_enabled:
            self.create_text(x + w/2, y + 80, text="🔀 分支", 
                            font=('Arial', 8), fill='#E65100', tags=tags)
                            
    def _draw_connection(self, from_id: str, to_id: str, conn_type: str):
        """绘制连线"""
        from_step = self.project.get_step(from_id)
        to_step = self.project.get_step(to_id)
        if not from_step or not to_step:
            return
            
        x1 = from_step.canvas_x + NODE_WIDTH
        y1 = from_step.canvas_y + NODE_HEIGHT / 2
        x2 = to_step.canvas_x
        y2 = to_step.canvas_y + NODE_HEIGHT / 2
        
        # 根据类型选择颜色
        if conn_type == 'match':
            color = '#4CAF50'  # 绿色
        elif conn_type == 'nomatch':
            color = '#F44336'  # 红色
        else:
            color = '#9E9E9E'  # 灰色主线
            
        # 绘制曲线
        mid_x = (x1 + x2) / 2
        self.create_line(x1, y1, mid_x, y1, mid_x, y2, x2, y2,
                        fill=color, width=2, smooth=True,
                        arrow=tk.LAST, tags=('connection', f'conn_{from_id}_{to_id}'))
                        
    def _is_connected(self, step_id: str) -> bool:
        """检查节点是否连接到主线"""
        if step_id in self.project.mainline_order:
            return True
        for step in self.project.steps.values():
            if step.branch_match_next == step_id or step.branch_nomatch_next == step_id:
                return True
        return False
        
    def _get_node_at(self, x, y) -> Optional[str]:
        """获取坐标处的节点ID"""
        items = self.find_overlapping(x-5, y-5, x+5, y+5)
        for item in items:
            tags = self.gettags(item)
            for tag in tags:
                if tag.startswith('node_'):
                    return tag[5:]
        return None
        
    def _on_click(self, event):
        """单击"""
        node_id = self._get_node_at(event.x, event.y)
        
        # 连线模式：第二次点击完成连线
        if self.drawing_connection:
            if node_id and node_id != self.connection_start:
                self._complete_connection(node_id)
            else:
                # 点击空白或自身，取消连线
                self.drawing_connection = False
                self.connection_start = None
                self.app.sv_status.set("连线已取消")
            self.redraw()
            return
        
        if node_id:
            if node_id not in self.selected_nodes:
                self.selected_nodes = [node_id]
            self.dragging = True
            self.drag_start = (event.x, event.y)
            self.drag_node = node_id
        else:
            self.selected_nodes = []
            # 开始框选
            self.box_selecting = True
            self.box_start = (event.x, event.y)
            
        self.redraw()
        self.app._sync_tree_selection()
        
    def _on_ctrl_click(self, event):
        """Ctrl+单击 - 多选"""
        node_id = self._get_node_at(event.x, event.y)
        if node_id:
            if node_id in self.selected_nodes:
                self.selected_nodes.remove(node_id)
            else:
                self.selected_nodes.append(node_id)
            self.redraw()
            self.app._sync_tree_selection()
            
    def _on_drag(self, event):
        """拖拽"""
        if self.dragging and self.drag_node:
            step = self.project.get_step(self.drag_node)
            if step:
                dx = event.x - self.drag_start[0]
                dy = event.y - self.drag_start[1]
                # 边界限制：确保节点不会被拖出画布可视区域
                new_x = max(0, step.canvas_x + dx)
                new_y = max(0, step.canvas_y + dy)
                step.canvas_x = new_x
                step.canvas_y = new_y
                self.drag_start = (event.x, event.y)
                self.redraw()
        elif self.box_selecting:
            # 绘制框选矩形
            if self.box_rect:
                self.delete(self.box_rect)
            self.box_rect = self.create_rectangle(
                self.box_start[0], self.box_start[1],
                event.x, event.y,
                outline='#2196F3', dash=(4, 4), width=2
            )
            
    def _on_release(self, event):
        """释放"""
        if self.box_selecting:
            # 框选完成，选中区域内节点
            if self.box_rect:
                self.delete(self.box_rect)
            x1, y1 = self.box_start
            x2, y2 = event.x, event.y
            left, right = min(x1, x2), max(x1, x2)
            top, bottom = min(y1, y2), max(y1, y2)
            
            self.selected_nodes = []
            for step in self.project.steps.values():
                cx = step.canvas_x + NODE_WIDTH / 2
                cy = step.canvas_y + NODE_HEIGHT / 2
                if left <= cx <= right and top <= cy <= bottom:
                    self.selected_nodes.append(step.id)
                    
            self.box_selecting = False
            self.redraw()
            self.app._sync_tree_selection()
            
        self.dragging = False
        self.drag_node = None
        
    def _on_right_click(self, event):
        """右键菜单"""
        node_id = self._get_node_at(event.x, event.y)
        if node_id:
            self.selected_nodes = [node_id]
            self.redraw()
            self._show_context_menu(event.x, event.y, node_id)
            
    def _show_context_menu(self, x, y, node_id):
        """显示右键菜单"""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="编辑步骤", command=lambda: self._edit_step(node_id))
        menu.add_command(label="添加分支连线...", command=lambda: self._start_connection(node_id))
        menu.add_separator()
        menu.add_command(label="删除步骤", command=lambda: self._delete_step(node_id))
        menu.add_command(label="复制步骤", command=lambda: self._copy_step(node_id))
        menu.tk_popup(self.winfo_rootx() + x, self.winfo_rooty() + y)
        
    def _edit_step(self, step_id: str):
        """编辑步骤"""
        step = self.project.get_step(step_id)
        if step:
            self.app._edit_step_dialog(step)
            
    def _start_connection(self, step_id: str):
        """开始绘制连线"""
        # 询问连接类型
        dialog = tk.Toplevel(self)
        dialog.title("选择连线类型")
        dialog.geometry("200x120")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        
        var = tk.StringVar(value='match')
        ttk.Radiobutton(dialog, text="匹配成功连线 (绿色)", variable=var, value='match').pack(anchor='w', padx=10, pady=4)
        ttk.Radiobutton(dialog, text="未匹配连线 (红色)", variable=var, value='nomatch').pack(anchor='w', padx=10)
        
        def on_ok():
            self.drawing_connection = True
            self.connection_start = step_id
            self.connection_type = var.get()
            dialog.destroy()
            self.app.sv_status.set(f"点击目标节点完成连线 (Esc取消)")
            
        def on_cancel():
            dialog.destroy()
            
        ttk.Button(dialog, text="确定", command=on_ok).pack(side='left', padx=20, pady=10)
        ttk.Button(dialog, text="取消", command=on_cancel).pack(side='left')
        
    def _complete_connection(self, target_id: str):
        """完成连线"""
        from_step = self.project.get_step(self.connection_start)
        if not from_step:
            self.drawing_connection = False
            self.connection_start = None
            return
            
        if self.connection_type == 'match':
            from_step.branch_match_next = target_id
        else:
            from_step.branch_nomatch_next = target_id
            
        from_step.branch_enabled = True
        self.drawing_connection = False
        self.connection_start = None
        self.connection_type = None
        self.app.sv_status.set(f"✅ 连线完成")
        self.app._sync_list_from_canvas()
        
    def _delete_step(self, step_id: str):
        """删除步骤"""
        if messagebox.askyesno("确认", "确定删除此步骤？"):
            self.project.remove_step(step_id)
            if step_id in self.selected_nodes:
                self.selected_nodes.remove(step_id)
            self.redraw()
            self.app._sync_list_from_canvas()
            
    def _copy_step(self, step_id: str):
        """复制步骤"""
        step = self.project.get_step(step_id)
        if step:
            new_step = copy.deepcopy(step)
            new_step.id = str(uuid.uuid4())[:8]
            new_step.canvas_x += 30
            new_step.canvas_y += 30
            new_step.branch_match_next = None
            new_step.branch_nomatch_next = None
            self.project.add_step(new_step, step_id)
            self.redraw()
            self.app._sync_list_from_canvas()
            
    def _on_double_click(self, event):
        """双击编辑"""
        node_id = self._get_node_at(event.x, event.y)
        if node_id:
            # 重置拖拽状态，防止双击后残留
            self.dragging = False
            self.drag_node = None
            self._edit_step(node_id)
            
    def _on_delete(self, event):
        """删除选中节点"""
        if self.selected_nodes:
            if messagebox.askyesno("确认", f"确定删除 {len(self.selected_nodes)} 个步骤？"):
                for sid in self.selected_nodes[:]:
                    self.project.remove_step(sid)
                self.selected_nodes = []
                self.redraw()
                self.app._sync_list_from_canvas()


# ═══════════════════════════════════════════════════════════════
#  AutoClickerApp — 主界面
# ═══════════════════════════════════════════════════════════════
class AutoClickerApp:

    def __init__(self, root):
        self.root = root
        self.root.title("🖱️ 连点器 Pro - Auto Clicker Pro")
        self.root.geometry("1100x800")
        self.root.minsize(900, 700)

        self.engine = ClickEngine()
        self.recorder = Recorder()
        self.flow_engine = FlowEngine()
        self.flow_project = FlowProject()

        self._picking = False
        self._pick_win = None
        self._kb_l = None
        self._clipboard_steps = []

        # 快捷键设置（持久化）
        self.hotkey_file = _APP_DIR / 'hotkey_settings.json'
        self.hotkeys = self._load_hotkeys()
        self.sv_hotkey_hint = tk.StringVar(value="")

        self._build_ui()
        self._start_kb_listener()
        self._tick_pos()

        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    # ════════════════ UI 构建 ════════════════

    def _build_ui(self):
        pad = dict(padx=10, pady=4)

        # ---- 顶部提示 ----
        top = ttk.Frame(self.root)
        top.pack(fill='x', **pad)
        ttk.Label(
            top,
            textvariable=self.sv_hotkey_hint,
            foreground='gray',
            font=('Microsoft YaHei UI', 8)
        ).pack(anchor='w')

        # ---- Notebook ----
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill='both', expand=True, **pad)

        f1 = ttk.Frame(self.nb, padding=12)
        self.nb.add(f1, text='  🖱️ 单点点击  ')
        self._build_manual_tab(f1)

        f2 = ttk.Frame(self.nb, padding=12)
        self.nb.add(f2, text='  🎬 操作录制  ')
        self._build_record_tab(f2)

        f3 = ttk.Frame(self.nb, padding=12)
        self.nb.add(f3, text='  📁 录制管理  ')
        self._build_manage_tab(f3)

        f4 = ttk.Frame(self.nb, padding=12)
        self.nb.add(f4, text='  ⚡ 高级模式  ')
        self._build_advanced_tab(f4)

        f5 = ttk.Frame(self.nb, padding=12)
        self.nb.add(f5, text='  ⌨️ 快捷键设置  ')
        self._build_hotkey_tab(f5)

        # ---- 状态栏 ----
        sbar = ttk.Frame(self.root, padding=(10, 4))
        sbar.pack(fill='x')
        self.sv_status = tk.StringVar(value="✅ 就绪")
        self.sv_pos = tk.StringVar(value="")
        self._update_hotkey_hint()
        ttk.Label(sbar, textvariable=self.sv_status).pack(side='left')
        ttk.Label(sbar, textvariable=self.sv_pos,
                  foreground='gray').pack(side='right')

    # ──────── Tab 1: 单点点击 ────────
    def _build_manual_tab(self, parent):
        row = 0
        parent.columnconfigure(0, weight=1)

        # ---- 点击位置 ----
        lf_pos = ttk.LabelFrame(parent, text="点击位置", padding=10)
        lf_pos.grid(row=row, column=0, sticky='ew', pady=(0, 8))
        row += 1

        f = ttk.Frame(lf_pos)
        f.pack(fill='x')
        ttk.Label(f, text="X:").pack(side='left')
        self.var_x = tk.IntVar(value=0)
        ttk.Spinbox(f, from_=0, to=9999, textvariable=self.var_x,
                     width=8).pack(side='left', padx=(0, 12))
        ttk.Label(f, text="Y:").pack(side='left')
        self.var_y = tk.IntVar(value=0)
        ttk.Spinbox(f, from_=0, to=9999, textvariable=self.var_y,
                     width=8).pack(side='left', padx=(0, 12))

        self.btn_pick = ttk.Button(f, text="📍 取点",
                                    command=self._pick_position)
        self.btn_pick.pack(side='left', padx=(0, 8))
        ttk.Button(f, text="📋 当前鼠标",
                   command=self._use_current_pos).pack(side='left')

        # ---- 点击设置 ----
        lf_set = ttk.LabelFrame(parent, text="点击设置", padding=10)
        lf_set.grid(row=row, column=0, sticky='ew', pady=(0, 8))
        row += 1

        # 点击类型
        f = ttk.Frame(lf_set); f.pack(fill='x', pady=3)
        ttk.Label(f, text="点击类型:", width=10,
                  anchor='e').pack(side='left')
        self.var_btn = tk.StringVar(value='left')
        for txt, val in [("左键", "left"), ("右键", "right"),
                         ("中键", "middle")]:
            ttk.Radiobutton(f, text=txt, variable=self.var_btn,
                            value=val).pack(side='left', padx=8)

        # 点击方式
        f = ttk.Frame(lf_set); f.pack(fill='x', pady=3)
        ttk.Label(f, text="点击方式:", width=10,
                  anchor='e').pack(side='left')
        self.var_click_type = tk.StringVar(value='single')
        for txt, val in [("单击", "single"), ("双击", "double")]:
            ttk.Radiobutton(f, text=txt, variable=self.var_click_type,
                            value=val).pack(side='left', padx=8)

        # 点击次数
        f = ttk.Frame(lf_set); f.pack(fill='x', pady=3)
        ttk.Label(f, text="点击次数:", width=10,
                  anchor='e').pack(side='left')
        self.var_count = tk.IntVar(value=1)
        ttk.Spinbox(f, from_=0, to=999999, textvariable=self.var_count,
                     width=10).pack(side='left')
        ttk.Label(f, text="(0 = 无限)",
                  foreground='gray').pack(side='left', padx=6)

        # 间隔时间
        f = ttk.Frame(lf_set); f.pack(fill='x', pady=3)
        ttk.Label(f, text="间隔时间:", width=10,
                  anchor='e').pack(side='left')
        self.var_interval = tk.IntVar(value=100)
        ttk.Spinbox(f, from_=1, to=999999, textvariable=self.var_interval,
                     width=10, increment=10).pack(side='left')
        ttk.Label(f, text="毫秒 (ms)",
                  foreground='gray').pack(side='left', padx=6)

        # 速度倍率
        f = ttk.Frame(lf_set); f.pack(fill='x', pady=3)
        ttk.Label(f, text="速度倍率:", width=10,
                  anchor='e').pack(side='left')
        self.var_speed = tk.DoubleVar(value=1.0)
        ttk.Scale(f, from_=0.1, to=10.0, variable=self.var_speed,
                  orient='horizontal', length=200).pack(side='left')
        self.lbl_speed = ttk.Label(f, text="1.0x", width=6)
        self.lbl_speed.pack(side='left', padx=4)
        self.var_speed.trace_add(
            'write',
            lambda *_: self.lbl_speed.config(
                text=f"{self.var_speed.get():.1f}x"
            )
        )

        # 容错范围（随机偏移半径）
        f = ttk.Frame(lf_set); f.pack(fill='x', pady=3)
        ttk.Label(f, text="容错范围:", width=10,
                  anchor='e').pack(side='left')
        self.var_radius = tk.IntVar(value=0)
        self.spb_radius = ttk.Spinbox(f, from_=0, to=30, textvariable=self.var_radius,
                     width=5, command=lambda: self._on_radius_change(
                         self.var_radius, self.canvas_radius_rec))
        self.spb_radius.pack(side='left')
        self.scale_radius = ttk.Scale(f, from_=0, to=30, variable=self.var_radius,
                                       orient='horizontal', length=120,
                                       command=lambda v: self._on_radius_change(
                                           self.var_radius, self.canvas_radius_rec))
        self.scale_radius.pack(side='left', padx=4)
        ttk.Label(f, text="(0~30)",
                  foreground='gray').pack(side='left')
        # 圆圈预览（先 pack right 确保可见）
        self.canvas_radius_rec = tk.Canvas(f, width=64, height=64,
                                            bg='white', highlightthickness=1,
                                            highlightbackground='#CCCCCC')
        self.canvas_radius_rec.pack(side='right', padx=8)
        self.canvas_radius_rec.update_idletasks()
        self._draw_radius_circle(self.canvas_radius_rec, 0)

        # ---- 操作按钮 ----
        bf = ttk.Frame(parent)
        bf.grid(row=row, column=0, pady=10)
        row += 1

        self.btn_start = ttk.Button(bf, text="▶ 开始点击",
                                     command=self._start_click, width=16)
        self.btn_start.pack(side='left', padx=8)
        self.btn_stop = ttk.Button(bf, text="■ 停止",
                                    command=self._stop_click, width=16,
                                    state='disabled')
        self.btn_stop.pack(side='left', padx=8)

        # 进度
        self.sv_progress = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self.sv_progress,
                  foreground='gray').grid(row=row, column=0)
        row += 1

    def _apply_edit(self, item_id, idx, delay_var, dialog, hold_var=None):
        """兼容旧接口，实际编辑已改为 inline 方式"""
        dialog.destroy()

    def _delete_event(self, idx, item_id, dialog=None):
        """删除事件行"""
        if dialog:
            try:
                dialog.destroy()
            except tk.TclError:
                pass
        self._current_events.pop(idx)
        self.tree_events.delete(item_id)
        for i, cid in enumerate(self.tree_events.get_children(), 1):
            vals = list(self.tree_events.item(cid, 'values'))
            vals[0] = i
            self.tree_events.item(cid, values=vals)
        self.sv_status.set(f"已删除，当前剩余 {len(self._current_events)} 步")

    # ──────── Tab 2: 操作录制 ────────
    def _build_record_tab(self, parent):
        # ---- 录制控制 ----
        lf = ttk.LabelFrame(parent, text="录制控制", padding=10)
        lf.pack(fill='x', pady=(0, 8))

        bf = ttk.Frame(lf); bf.pack(fill='x')
        self.btn_rec_start = ttk.Button(bf, text="● 开始录制",
                                         command=self._start_rec, width=14)
        self.btn_rec_start.pack(side='left', padx=4)
        self.btn_rec_stop = ttk.Button(bf, text="■ 停止录制",
                                        command=self._stop_rec, width=14,
                                        state='disabled')
        self.btn_rec_stop.pack(side='left', padx=4)
        # 在此插入按钮
        self.btn_insert_rec = ttk.Button(bf, text="➕ 在此插入",
                                          command=self._start_insert_rec, width=14,
                                          state='disabled')
        self.btn_insert_rec.pack(side='left', padx=4)
        self.sv_rec_status = tk.StringVar(value="未录制")
        cur_vrect = _get_virtual_screen_rect()
        cur_w, cur_h = cur_vrect[2], cur_vrect[3]
        ttk.Label(bf, textvariable=self.sv_rec_status,
                  foreground='gray').pack(side='right')

        # 录制选项
        of = ttk.Frame(lf); of.pack(fill='x', pady=(6, 0))
        self.var_rec_mouse = tk.BooleanVar(value=True)
        ttk.Checkbutton(of, text="录制鼠标点击/拖动",
                        variable=self.var_rec_mouse).pack(side='left', padx=(0, 16))
        self.var_rec_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(of, text="录制键盘按键",
                        variable=self.var_rec_key).pack(side='left', padx=(0, 16))
        self.var_rec_drag = tk.BooleanVar(value=True)
        ttk.Checkbutton(of, text="录制拖动操作",
                        variable=self.var_rec_drag).pack(side='left', padx=(0, 16))
        self.var_rec_move = tk.BooleanVar(value=False)
        ttk.Checkbutton(of, text="录制鼠标轨迹（全程）",
                        variable=self.var_rec_move).pack(side='left')

        # ---- 事件列表 ----
        lf2 = ttk.LabelFrame(parent, text="录制事件", padding=10)
        lf2.pack(fill='both', expand=True, pady=(0, 8))

        # 事件列表工具栏：显示/隐藏移动轨迹
        ev_toolbar = ttk.Frame(lf2)
        ev_toolbar.pack(fill='x', pady=(0, 4))
        self.var_show_moves = tk.BooleanVar(value=False)
        ttk.Checkbutton(ev_toolbar, text="显示移动轨迹",
                        variable=self.var_show_moves,
                        command=self._toggle_move_visibility).pack(side='left')
        ttk.Label(ev_toolbar, text="(默认隐藏，勾选后显示所有移动事件)",
                  foreground='gray', font=('Microsoft YaHei UI', 8)).pack(side='left', padx=8)

        cols = ('seq', 'type', 'pos', 'button', 'time', 'hold', 'delay')
        self.tree_events = ttk.Treeview(lf2, columns=cols,
                                         show='headings', height=8)
        self.tree_events.heading('seq',    text='#')
        self.tree_events.heading('type',   text='类型')
        self.tree_events.heading('pos',    text='位置')
        self.tree_events.heading('button', text='按键')
        self.tree_events.heading('time',   text='发生时间')
        self.tree_events.heading('hold',   text='按住(s)')
        self.tree_events.heading('delay',  text='延迟(s)')
        self.tree_events.column('seq',    width=35,  anchor='center')
        self.tree_events.column('type',   width=55,  anchor='center')
        self.tree_events.column('pos',    width=170, anchor='center')
        self.tree_events.column('button', width=55,  anchor='center')
        self.tree_events.column('time',   width=90,  anchor='center')
        self.tree_events.column('hold',   width=65,  anchor='center')
        self.tree_events.column('delay',  width=65,  anchor='center')

        # 可编辑列高亮样式
        self.tree_events.tag_configure('editable_cell', foreground='#1565C0',
                                        font=('Consolas', 9, 'underline'))
        # 各类事件背景色（浅色，不影响字体）
        # 移动
        self.tree_events.tag_configure('move_child', foreground='#666666',
                                        background='#E8F5E9',
                                        font=('Consolas', 8))
        # 移动折叠组（稍深）
        self.tree_events.tag_configure('move_group', foreground='#2E7D32',
                                        background='#C8E6C9',
                                        font=('Microsoft YaHei UI', 9))
        # 点击
        self.tree_events.tag_configure('click_row', foreground='#1A237E',
                                        background='#E3F2FD',
                                        font=('Microsoft YaHei UI', 9, 'bold'))
        # 拖动
        self.tree_events.tag_configure('drag_row', foreground='#E65100',
                                        background='#FFF3E0',
                                        font=('Microsoft YaHei UI', 9, 'bold'))
        # 键盘按键
        self.tree_events.tag_configure('key_row', foreground='#4A148C',
                                        background='#F3E5F5',
                                        font=('Microsoft YaHei UI', 9, 'bold'))
        # 插入位置标记
        self.tree_events.tag_configure('insert_marker', foreground='#B71C1C',
                                        background='#FFEB3B',
                                        font=('Microsoft YaHei UI', 9, 'bold'))
        # 插入操作（斜体，不参与原编号）
        self.tree_events.tag_configure('inserted_row', font=('Consolas', 9, 'italic'),
                                        foreground='#00695C')

        # 事件类型 → 标签名映射
        self._ev_type_tags = {
            'move': 'move_child', 'click': 'click_row',
            'drag': 'drag_row', 'key': 'key_row',
        }

        sb = ttk.Scrollbar(lf2, orient='vertical',
                           command=self.tree_events.yview)
        self.tree_events.configure(yscrollcommand=sb.set)
        self.tree_events.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')

        # ---- Inline 编辑：点击 delay 或 hold 列时弹出 Entry 覆盖 ----
        self._inline_entry = None      # 当前活跃的编辑 Entry
        self._inline_item = None       # 正在编辑的 item id
        self._inline_col = None        # 正在编辑的列名

        def _commit_inline():
            """提交 inline 编辑的值"""
            if self._inline_entry is None:
                return
            try:
                new_val = float(self._inline_entry.get())
                new_val = max(0.0, new_val)
            except ValueError:
                new_val = 0.0
            item = self._inline_item
            col = self._inline_col
            # 用 seq 号定位事件（兼容 move 子行和插入事件）
            vals = list(self.tree_events.item(item, 'values'))
            try:
                seq_num = int(vals[0])
                idx = seq_num - 1  # 1-based → 0-based
            except (ValueError, TypeError):
                # "插入N" 格式：遍历 _current_events 找到对应事件
                seq_str = str(vals[0])
                idx = None
                if seq_str.startswith('插入'):
                    try:
                        insert_num = int(seq_str[2:])
                        for k, ev in enumerate(self._current_events):
                            if ev.get('_is_insert') and ev.get('_insert_num') == insert_num:
                                idx = k
                                break
                    except ValueError:
                        pass
                if idx is None:
                    try:
                        idx = self.tree_events.index(item)
                    except Exception:
                        idx = 0
            if idx < len(self._current_events):
                ev = self._current_events[idx]
                if col == 'delay':
                    ev['_extra_delay'] = new_val
                elif col == 'hold':
                    ev['hold_duration'] = new_val
                    if ev.get('type') == 'click':
                        ev['release_time'] = round(ev['time'] + new_val, 3)
            # 更新显示
            if col == 'delay':
                vals[6] = f"{new_val:.3f}" if new_val != 0 else '0.000'
            elif col == 'hold':
                vals[5] = f"{new_val:.3f}" if new_val != 0 else '0.000'
            self.tree_events.item(item, values=vals)
            _destroy_inline()

        def _destroy_inline():
            if self._inline_entry:
                try:
                    self._inline_entry.destroy()
                except tk.TclError:
                    pass
                self._inline_entry = None
                self._inline_item = None
                self._inline_col = None

        def _start_inline_edit(item_id, col_name):
            """在指定单元格上创建 inline Entry 编辑框"""
            _commit_inline()  # 先提交之前的编辑
            # 获取单元格位置
            bbox = self.tree_events.bbox(item_id, col_name)
            if not bbox:
                return
            x, y, w, h = bbox
            # 用 seq 号定位事件（兼容 move 子行和插入事件）
            displayed_vals = list(self.tree_events.item(item_id, 'values'))
            try:
                seq_num = int(displayed_vals[0])
                idx = seq_num - 1
            except (ValueError, TypeError):
                seq_str = str(displayed_vals[0])
                idx = None
                if seq_str.startswith('插入'):
                    try:
                        insert_num = int(seq_str[2:])
                        for k, ev in enumerate(self._current_events):
                            if ev.get('_is_insert') and ev.get('_insert_num') == insert_num:
                                idx = k
                                break
                    except ValueError:
                        pass
                if idx is None:
                    try:
                        idx = self.tree_events.index(item_id)
                    except Exception:
                        idx = 0
            if idx >= len(self._current_events):
                return
            ev = self._current_events[idx]
            if col_name == 'hold' and ev.get('type') == 'drag':
                return  # 拖动事件不可编辑按住时长（由拖动距离决定）
            # 从显示值读取（避免 calculated delay 被重置为 0）
            displayed_vals = list(self.tree_events.item(item_id, 'values'))
            if col_name == 'delay':
                current_val = str(displayed_vals[6])  # delay 列（index 6）
            elif col_name == 'hold':
                current_val = str(displayed_vals[5])  # hold 列（index 5）
            else:
                return
            # 创建 Entry
            entry = tk.Entry(self.tree_events, font=('Consolas', 9),
                             width=8, relief='solid', bd=1)
            entry.insert(0, current_val)
            entry.select_range(0, tk.END)
            entry.focus_set()
            entry.place(x=x, y=y, width=w, height=h)
            self._inline_entry = entry
            self._inline_item = item_id
            self._inline_col = col_name
            entry.bind('<Return>', lambda e: _commit_inline())
            entry.bind('<Escape>', lambda e: _destroy_inline())
            entry.bind('<FocusOut>', lambda e: _commit_inline())

        def _on_tree_click(event):
            col = self.tree_events.identify_column(event.x)
            item_id = self.tree_events.identify_row(event.y)
            if not item_id or not col:
                _commit_inline()
                return
            # 移动折叠组：点击展开/折叠
            tags = self.tree_events.item(item_id, 'tags')
            if 'move_group' in tags:
                _commit_inline()
                # 切换展开状态
                children = self.tree_events.get_children(item_id)
                if children:
                    current_open = self.tree_events.item(item_id, 'open')
                    self.tree_events.item(item_id, open=not current_open)
                return
            col_num = int(col.replace('#', ''))
            col_name = cols[col_num - 1]  # 映射到列名
            if col_name in ('delay', 'hold'):
                _start_inline_edit(item_id, col_name)
            else:
                _commit_inline()

        self.tree_events.bind('<Button-1>', _on_tree_click)

        # 双击展开/折叠移动组
        def _on_tree_dblclick(event):
            item_id = self.tree_events.identify_row(event.y)
            if not item_id:
                return
            tags = self.tree_events.item(item_id, 'tags')
            if 'move_group' in tags:
                children = self.tree_events.get_children(item_id)
                if children:
                    current_open = self.tree_events.item(item_id, 'open')
                    self.tree_events.item(item_id, open=not current_open)

        self.tree_events.bind('<Double-Button-1>', _on_tree_dblclick)

        self._current_events = []   # 当前编辑中的事件列表
        self._insert_counter = 0    # 插入操作计数器

        # ---- 复现与保存 ----
        lf3 = ttk.LabelFrame(parent, text="复现与保存", padding=10)
        lf3.pack(fill='x')

        # 速度
        f = ttk.Frame(lf3); f.pack(fill='x', pady=3)
        ttk.Label(f, text="复现速度:", width=10,
                  anchor='e').pack(side='left')
        self.var_play_speed = tk.DoubleVar(value=1.0)
        ttk.Scale(f, from_=0.1, to=10.0, variable=self.var_play_speed,
                  orient='horizontal', length=160).pack(side='left')
        self.lbl_play_speed = ttk.Label(f, text="1.0x", width=6)
        self.lbl_play_speed.pack(side='left', padx=4)
        self.var_play_speed.trace_add(
            'write',
            lambda *_: self.lbl_play_speed.config(
                text=f"{self.var_play_speed.get():.1f}x"
            )
        )
        self.var_loop = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="循环播放",
                        variable=self.var_loop).pack(side='left', padx=12)

        # 容错范围
        f2 = ttk.Frame(lf3); f2.pack(fill='x', pady=3)
        ttk.Label(f2, text="容错范围:", width=10,
                  anchor='e').pack(side='left')
        self.var_play_radius = tk.IntVar(value=0)
        self.spb_play_radius = ttk.Spinbox(f2, from_=0, to=30, textvariable=self.var_play_radius,
                     width=5, command=lambda: self._on_radius_change(
                         self.var_play_radius, self.canvas_play_radius))
        self.spb_play_radius.pack(side='left')
        self.scale_play_radius = ttk.Scale(f2, from_=0, to=30, variable=self.var_play_radius,
                                            orient='horizontal', length=120,
                                            command=lambda v: self._on_radius_change(
                                                self.var_play_radius, self.canvas_play_radius))
        self.scale_play_radius.pack(side='left', padx=4)
        ttk.Label(f2, text="(0~30)",
                  foreground='gray').pack(side='left')
        # 圆圈预览
        self.canvas_play_radius = tk.Canvas(f2, width=64, height=64,
                                             bg='white', highlightthickness=1,
                                             highlightbackground='#CCCCCC')
        self.canvas_play_radius.pack(side='right', padx=8)
        self.canvas_play_radius.update_idletasks()
        self._draw_radius_circle(self.canvas_play_radius, 0)

        # 按钮
        bf2 = ttk.Frame(lf3); bf2.pack(fill='x', pady=(6, 0))
        self.btn_play = ttk.Button(bf2, text="▶ 复现",
                                    command=self._play_rec, width=12)
        self.btn_play.pack(side='left', padx=4)
        self.btn_stop_play = ttk.Button(bf2, text="■ 停止",
                                         command=self._stop_play_rec,
                                         width=12, state='disabled')
        self.btn_stop_play.pack(side='left', padx=4)

        # 保存
        sf = ttk.Frame(lf3); sf.pack(fill='x', pady=(8, 0))
        ttk.Label(sf, text="保存名称:").pack(side='left')
        self.var_save_name = tk.StringVar(
            value=f"录制_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        ttk.Entry(sf, textvariable=self.var_save_name,
                  width=28).pack(side='left', padx=4)
        ttk.Button(sf, text="💾 保存", command=self._save_rec,
                   width=8).pack(side='left', padx=4)

        self.sv_play_progress = tk.StringVar(value="")
        ttk.Label(lf3, textvariable=self.sv_play_progress,
                  foreground='gray').pack(anchor='w', pady=(4, 0))

    # ──────── Tab 3: 录制管理 ────────
    def _build_manage_tab(self, parent):
        # 工具栏
        tb = ttk.Frame(parent)
        tb.pack(fill='x', pady=(0, 8))
        ttk.Button(tb, text="🔄 刷新", command=self._refresh_list,
                   width=8).pack(side='left', padx=4)
        ttk.Button(tb, text="📂 打开文件夹", command=self._open_folder,
                   width=14).pack(side='left', padx=4)

        # 列表
        cols = ('name', 'count', 'duration', 'res', 'created')
        self.tree_files = ttk.Treeview(parent, columns=cols,
                                        show='headings', height=14)
        self.tree_files.heading('name',    text='名称')
        self.tree_files.heading('count',   text='事件数')
        self.tree_files.heading('duration', text='时长(s)')
        self.tree_files.heading('res',     text='录制分辨率')
        self.tree_files.heading('created', text='创建时间')
        self.tree_files.column('name',    width=180)
        self.tree_files.column('count',   width=60,  anchor='center')
        self.tree_files.column('duration', width=60,  anchor='center')
        self.tree_files.column('res',     width=100, anchor='center')
        self.tree_files.column('created', width=150)

        sb = ttk.Scrollbar(parent, orient='vertical',
                           command=self.tree_files.yview)
        self.tree_files.configure(yscrollcommand=sb.set)
        self.tree_files.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')

        # 双击加载
        self.tree_files.bind('<Double-1>', lambda e: self._load_recording_only())

        # 操作按钮
        bf = ttk.Frame(parent)
        bf.pack(fill='x', pady=(8, 0))
        ttk.Button(bf, text="▶ 加载并复现",
                   command=self._load_and_play, width=14).pack(
                       side='left', padx=4)
        ttk.Button(bf, text="📋 查看步骤",
                   command=self._load_recording_only, width=14).pack(
                       side='left', padx=4)
        ttk.Button(bf, text="✏️ 重命名",
                   command=self._rename_file, width=10).pack(
                       side='left', padx=4)
        ttk.Button(bf, text="🗑️ 删除",
                   command=self._delete_file, width=8).pack(
                       side='left', padx=4)

        self._recordings_cache = []
        self._refresh_list()

    # ──────── Tab 4: 高级模式 ────────
    def _build_advanced_tab(self, parent):
        # 工具栏
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill='x', pady=(0, 8))
        
        ttk.Button(toolbar, text="➕ 新建步骤", command=self._add_step, width=10).pack(side='left', padx=2)
        ttk.Button(toolbar, text="✏️ 编辑", command=self._edit_selected_step, width=8).pack(side='left', padx=2)
        ttk.Button(toolbar, text="🗑️ 删除", command=self._delete_selected_steps, width=8).pack(side='left', padx=2)
        ttk.Button(toolbar, text="📋 复制", command=self._copy_selected_steps, width=8).pack(side='left', padx=2)
        ttk.Button(toolbar, text="📄 粘贴", command=self._paste_steps, width=8).pack(side='left', padx=2)
        
        ttk.Separator(toolbar, orient='vertical').pack(side='left', fill='y', padx=8)
        
        ttk.Button(toolbar, text="💾 保存流程", command=self._save_flow, width=10).pack(side='left', padx=2)
        ttk.Button(toolbar, text="📂 加载流程", command=self._load_flow, width=10).pack(side='left', padx=2)
        
        ttk.Separator(toolbar, orient='vertical').pack(side='left', fill='y', padx=8)
        
        ttk.Button(toolbar, text="▶ 运行流程", command=self._run_flow, width=10).pack(side='left', padx=2)
        self.btn_stop_flow = ttk.Button(toolbar, text="■ 停止", command=self._stop_flow, width=8, state='disabled')
        self.btn_stop_flow.pack(side='left', padx=2)
        
        # 主分割面板
        paned = ttk.PanedWindow(parent, orient='horizontal')
        paned.pack(fill='both', expand=True)
        
        # 左侧：流程图
        flow_frame = ttk.LabelFrame(paned, text="流程图", padding=4)
        paned.add(flow_frame, weight=2)
        
        self.flow_canvas = FlowCanvas(flow_frame, self, bg='white')
        self.flow_canvas.pack(fill='both', expand=True)
        self.flow_canvas.set_project(self.flow_project)
        
        # 右侧：步骤列表
        list_frame = ttk.LabelFrame(paned, text="步骤列表", padding=4)
        paned.add(list_frame, weight=1)
        
        # 列表
        cols = ('desc', 'op', 'match', 'delay')
        self.tree_flow = ttk.Treeview(list_frame, columns=cols, show='tree headings', height=15)
        self.tree_flow.heading('#0', text='#')
        self.tree_flow.heading('desc', text='描述')
        self.tree_flow.heading('op', text='操作')
        self.tree_flow.heading('match', text='匹配')
        self.tree_flow.heading('delay', text='延时')
        self.tree_flow.column('#0', width=30)
        self.tree_flow.column('desc', width=120)
        self.tree_flow.column('op', width=60)
        self.tree_flow.column('match', width=50)
        self.tree_flow.column('delay', width=60)
        
        sb = ttk.Scrollbar(list_frame, orient='vertical', command=self.tree_flow.yview)
        self.tree_flow.configure(yscrollcommand=sb.set)
        self.tree_flow.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        
        # 列表右键菜单
        self.tree_flow.bind('<Button-3>', self._on_list_right_click)
        self.tree_flow.bind('<Double-1>', lambda e: self._edit_selected_step())
        self.tree_flow.bind('<Control-Button-1>', self._on_list_ctrl_click)
        
        # 列表选择同步到画布
        self.tree_flow.bind('<<TreeviewSelect>>', self._on_list_select)
        
        # 底部进度
        self.sv_flow_progress = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self.sv_flow_progress,
                  foreground='gray').pack(anchor='w', pady=4)
        
        # 初始布局
        self._init_flow_layout()

    def _init_flow_layout(self):
        """初始化流程布局"""
        # 设置默认画布滚动区域
        self.flow_canvas.configure(scrollregion=(0, 0, 2000, 2000))
        
    # ════════════════ 高级模式操作 ════════════════
    
    def _add_step(self):
        """添加新步骤"""
        step = FlowStep()
        step.description = f"步骤 {len(self.flow_project.steps) + 1}"
        
        # 计算位置
        mainline = self.flow_project.get_mainline_steps()
        if mainline:
            last = mainline[-1]
            step.canvas_x = last.canvas_x + NODE_WIDTH + 60
            step.canvas_y = last.canvas_y
        else:
            step.canvas_x = 50
            step.canvas_y = 100
            
        self.flow_project.add_step(step)
        self._refresh_flow_ui()
        
    def _edit_selected_step(self):
        """编辑选中的步骤"""
        # 从列表获取选中
        sel = self.tree_flow.selection()
        if not sel:
            # 从画布获取
            if self.flow_canvas.selected_nodes:
                step = self.flow_project.get_step(self.flow_canvas.selected_nodes[0])
                if step:
                    self._edit_step_dialog(step)
            return
            
        step_id = sel[0]
        step = self.flow_project.get_step(step_id)
        if step:
            self._edit_step_dialog(step)
            
    def _edit_step_dialog(self, step: FlowStep):
        """打开步骤编辑对话框"""
        dialog = StepEditDialog(self.root, step, self.flow_project)
        self.root.wait_window(dialog)
        if dialog.result:
            self._refresh_flow_ui()
            
    def _delete_selected_steps(self):
        """删除选中的步骤"""
        # 合并列表和画布选择
        to_delete = set()
        
        sel = self.tree_flow.selection()
        for sid in sel:
            to_delete.add(sid)
            
        for sid in self.flow_canvas.selected_nodes:
            to_delete.add(sid)
            
        if not to_delete:
            return
            
        if messagebox.askyesno("确认", f"确定删除 {len(to_delete)} 个步骤？"):
            for sid in to_delete:
                self.flow_project.remove_step(sid)
            self._refresh_flow_ui()
            
    def _copy_selected_steps(self):
        """复制选中的步骤"""
        self._clipboard_steps = []
        
        sel = self.tree_flow.selection()
        for sid in sel:
            step = self.flow_project.get_step(sid)
            if step:
                self._clipboard_steps.append(copy.deepcopy(step))
                
        for sid in self.flow_canvas.selected_nodes:
            step = self.flow_project.get_step(sid)
            if step:
                self._clipboard_steps.append(copy.deepcopy(step))
                
        if self._clipboard_steps:
            self.sv_status.set(f"已复制 {len(self._clipboard_steps)} 个步骤")
            
    def _paste_steps(self):
        """粘贴步骤"""
        if not self._clipboard_steps:
            messagebox.showinfo("提示", "剪贴板为空")
            return
            
        # 确定粘贴位置
        after_id = None
        sel = self.tree_flow.selection()
        if sel:
            after_id = sel[-1]
            
        for step in self._clipboard_steps:
            new_step = copy.deepcopy(step)
            new_step.id = str(uuid.uuid4())[:8]
            new_step.canvas_x += 30
            new_step.canvas_y += 30
            new_step.branch_match_next = None
            new_step.branch_nomatch_next = None
            self.flow_project.add_step(new_step, after_id)
            
        self._refresh_flow_ui()
        self.sv_status.set(f"已粘贴 {len(self._clipboard_steps)} 个步骤")
        
    def _refresh_flow_ui(self):
        """刷新流程UI"""
        self.flow_canvas.redraw()
        self._sync_list_from_canvas()
        
    def _sync_list_from_canvas(self):
        """从画布同步列表"""
        # 保存当前选择
        old_sel = self.tree_flow.selection()
        
        # 清空列表
        for item in self.tree_flow.get_children():
            self.tree_flow.delete(item)
            
        # 按主线顺序添加
        for i, step_id in enumerate(self.flow_project.mainline_order, 1):
            step = self.flow_project.get_step(step_id)
            if step:
                self.tree_flow.insert('', 'end', iid=step_id, values=(
                    step.description[:20] or step.id,
                    OP_NAMES.get(step.operation, step.operation),
                    "截图" if step.match_type == MATCH_IMAGE else "坐标",
                    f"{step.delay_after}ms"
                ), text=str(i))
                
                # 分支节点
                if step.branch_enabled:
                    # 匹配分支
                    if step.branch_match_next:
                        branch_step = self.flow_project.get_step(step.branch_match_next)
                        if branch_step:
                            self.tree_flow.insert(step_id, 'end', iid=f"{step_id}_match",
                                                  values=(
                                                      f"→ {branch_step.description[:15] or branch_step.id}",
                                                      OP_NAMES.get(branch_step.operation, ''),
                                                      '',
                                                      f"{branch_step.delay_after}ms"
                                                  ), text="✓")
                    # 未匹配分支
                    if step.branch_nomatch_next:
                        branch_step = self.flow_project.get_step(step.branch_nomatch_next)
                        if branch_step:
                            self.tree_flow.insert(step_id, 'end', iid=f"{step_id}_nomatch",
                                                  values=(
                                                      f"→ {branch_step.description[:15] or branch_step.id}",
                                                      OP_NAMES.get(branch_step.operation, ''),
                                                      '',
                                                      f"{branch_step.delay_after}ms"
                                                  ), text="✗")
        
        # 恢复选择
        for sid in old_sel:
            if self.tree_flow.exists(sid):
                self.tree_flow.selection_add(sid)
                
    def _on_list_select(self, event):
        """列表选择同步到画布"""
        sel = self.tree_flow.selection()
        if sel:
            # 提取真实步骤ID（去掉_match和_nomatch后缀）
            real_ids = []
            for sid in sel:
                if sid.endswith('_match') or sid.endswith('_nomatch'):
                    continue
                real_ids.append(sid)
            self.flow_canvas.selected_nodes = real_ids
            self.flow_canvas.redraw()
            
    def _sync_tree_selection(self):
        """画布选择同步到列表"""
        self.tree_flow.selection_remove(*self.tree_flow.get_children())
        for sid in self.flow_canvas.selected_nodes:
            if self.tree_flow.exists(sid):
                self.tree_flow.selection_add(sid)
            
    def _on_list_right_click(self, event):
        """列表右键菜单"""
        item = self.tree_flow.identify_row(event.y)
        if item:
            # 过滤分支节点
            if '_match' in item or '_nomatch' in item:
                return
            self.tree_flow.selection_set(item)
            
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="编辑", command=self._edit_selected_step)
            menu.add_command(label="删除", command=self._delete_selected_steps)
            menu.add_command(label="复制", command=self._copy_selected_steps)
            menu.add_separator()
            menu.add_command(label="添加分支连线", command=lambda: self._add_branch_from_list(item))
            menu.tk_popup(event.x_root, event.y_root)
            
    def _on_list_ctrl_click(self, event):
        """列表Ctrl+点击多选"""
        item = self.tree_flow.identify_row(event.y)
        if item and '_match' not in item and '_nomatch' not in item:
            if self.tree_flow.selection_includes(item):
                self.tree_flow.selection_remove(item)
            else:
                self.tree_flow.selection_add(item)
                
    def _add_branch_from_list(self, step_id: str):
        """从列表添加分支连线"""
        self.flow_canvas._start_connection(step_id)
        
    def _save_flow(self):
        """保存流程"""
        name = simpledialog.askstring("保存流程", "输入流程名称:",
                                      initialvalue=self.flow_project.name)
        if name:
            self.flow_project.name = name
            path = _APP_DIR / "flows" / f"{name}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.flow_project.to_dict(), f, ensure_ascii=False, indent=2)
                
            self.sv_status.set(f"✅ 已保存: {path}")
            
    def _load_flow(self):
        """加载流程"""
        flows_dir = _APP_DIR / "flows"
        if not flows_dir.exists():
            messagebox.showinfo("提示", "没有已保存的流程")
            return
            
        files = list(flows_dir.glob("*.json"))
        if not files:
            messagebox.showinfo("提示", "没有已保存的流程")
            return
            
        # 选择对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("选择流程")
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="选择要加载的流程:").pack(anchor='w', padx=10, pady=8)
        
        lb = tk.Listbox(dialog, height=12)
        lb.pack(fill='both', expand=True, padx=10, pady=4)
        for f in files:
            lb.insert('end', f.stem)
            
        def on_load():
            sel = lb.curselection()
            if sel:
                path = files[sel[0]]
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.flow_project = FlowProject.from_dict(data)
                self.flow_canvas.set_project(self.flow_project)
                self._refresh_flow_ui()
                self.sv_status.set(f"✅ 已加载: {path.stem}")
            dialog.destroy()
            
        ttk.Button(dialog, text="加载", command=on_load).pack(side='left', padx=20, pady=10)
        ttk.Button(dialog, text="取消", command=dialog.destroy).pack(side='left')
        
    def _run_flow(self):
        """运行流程"""
        if not self.flow_project.mainline_order:
            messagebox.showinfo("提示", "请先添加步骤")
            return
            
        self.btn_stop_flow.config(state='normal')
        self.sv_status.set("🔄 运行中...")
        
        def on_step_start(step_id):
            self.root.after(0, lambda: self._highlight_step(step_id))
            
        def on_step_done(step_id, success):
            pass
            
        def on_done(err):
            self.root.after(0, lambda: self._flow_finished(err))
            
        self.flow_engine.run(self.flow_project, on_step_start, on_step_done, on_done)
        
    def _highlight_step(self, step_id):
        """高亮当前步骤"""
        self.flow_canvas.redraw()
        self.sv_flow_progress.set(f"执行: {step_id}")
        
    def _flow_finished(self, err):
        """流程完成"""
        self.btn_stop_flow.config(state='disabled')
        if err:
            self.sv_status.set(f"⚠️ {err}")
        else:
            self.sv_status.set("✅ 流程完成")
        self.sv_flow_progress.set("")
        self.flow_canvas.redraw()
        
    def _stop_flow(self):
        """停止流程"""
        self.flow_engine.stop()
        self.sv_status.set("✅ 已停止")

    # ════════════════ 手动点击逻辑 ════════════════

    def _use_current_pos(self):
        x, y = pyautogui.position()
        self.var_x.set(x)
        self.var_y.set(y)
        self.sv_status.set(f"✅ 已获取鼠标位置: ({x}, {y})")

    def _pick_position(self):
        if self._picking:
            self._cancel_pick()
            return
        self._picking = True
        self.btn_pick.config(text="⏳ 点击屏幕取点...")
        self.sv_status.set("📍 请点击屏幕任意位置取点 (Esc 取消)")
        self.root.iconify()
        time.sleep(0.3)
        
        # 创建全屏透明窗口
        self._pick_win = tk.Toplevel(self.root)
        self._pick_win.attributes('-fullscreen', True)
        self._pick_win.attributes('-topmost', True)
        self._pick_win.attributes('-alpha', 0.01)  # 几乎透明
        self._pick_win.configure(bg='black', cursor='cross')
        
        # 提示标签
        label = tk.Label(self._pick_win, text="点击屏幕任意位置获取坐标 (Esc取消)", 
                        fg='white', bg='black', font=('Arial', 14))
        label.place(relx=0.5, rely=0.05, anchor='center')
        
        def on_click(event):
            self._picking = False
            x, y = event.x_root, event.y_root
            self._pick_win.destroy()
            self._pick_win = None
            self._finish_pick(x, y)
            
        def on_escape(event):
            self._cancel_pick()
            
        self._pick_win.bind('<Button-1>', on_click)
        self._pick_win.bind('<Escape>', on_escape)
        self._pick_win.focus_set()

    def _finish_pick(self, x, y):
        self.var_x.set(x)
        self.var_y.set(y)
        self.btn_pick.config(text="📍 取点")
        self.sv_status.set(f"✅ 取点成功: ({x}, {y})")
        self.root.deiconify()

    def _cancel_pick(self):
        self._picking = False
        if self._pick_win:
            self._pick_win.destroy()
            self._pick_win = None
        self.btn_pick.config(text="📍 取点")
        self.sv_status.set("✅ 已取消取点")
        self.root.deiconify()

    def _start_click(self):
        try:
            x        = self.var_x.get()
            y        = self.var_y.get()
            count    = self.var_count.get()
            interval = self.var_interval.get()
            button   = self.var_btn.get()
            speed    = self.var_speed.get()
            ctype    = self.var_click_type.get()
            radius   = self.var_radius.get()
        except tk.TclError:
            messagebox.showwarning("参数错误", "请检查输入参数是否正确")
            return

        if interval < 1:
            messagebox.showwarning("参数错误", "间隔时间不能小于 1ms")
            return

        self.btn_start.config(state='disabled')
        self.btn_stop.config(state='normal')
        self.sv_status.set(f"🔄 点击中… 位置:({x},{y})")

        actual_count = count * 2 if ctype == 'double' and count > 0 else count

        def on_progress(clicked, total):
            if ctype == 'double':
                display_clicked = clicked // 2
                display_total   = total // 2 if total > 0 else 0
                if total > 0:
                    self.sv_progress.set(f"已双击: {display_clicked}/{display_total}")
                else:
                    self.sv_progress.set(f"已双击: {display_clicked} (无限)")
            else:
                if total > 0:
                    self.sv_progress.set(f"已点击: {clicked}/{total}")
                else:
                    self.sv_progress.set(f"已点击: {clicked} (无限)")

        def on_done(err):
            self.root.after(0, lambda: self._click_finished(err))

        if ctype == 'double':
            self._start_double_click(x, y, count, interval, button, speed, radius, on_progress, on_done)
        else:
            self.engine.start(x, y, actual_count, interval, button, speed, radius, on_progress, on_done)

    def _start_double_click(self, x, y, count, interval_ms, button, speed, radius, on_progress, on_done):
        # 使用 ClickEngine 的公开接口启动，避免直接操作私有变量
        if self.engine.running:
            return

        # 设置 engine 为运行状态，确保全局停止按钮可以停止双击
        with self.engine._lock:
            self.engine._running = True

        def _loop():
            interval = max(interval_ms / 1000.0 / speed, 0.005)
            clicked = 0
            err = None
            try:
                while True:
                    with self.engine._lock:
                        if not self.engine._running:
                            break
                    if 0 < count <= clicked:
                        break
                    dx, dy = ClickEngine._random_offset(radius)
                    pyautogui.click(x=int(x) + dx, y=int(y) + dy, button=button)
                    time.sleep(0.01)
                    pyautogui.click(x=int(x) + dx, y=int(y) + dy, button=button)
                    clicked += 1
                    if on_progress:
                        try:
                            on_progress(clicked, count)
                        except Exception:
                            pass
                    if 0 < count <= clicked:
                        break
                    time.sleep(interval)
            except pyautogui.FailSafeException:
                err = "安全退出：鼠标已移至屏幕左上角"
            except Exception as e:
                err = str(e)
            finally:
                with self.engine._lock:
                    self.engine._running = False
                if on_done:
                    try:
                        on_done(err)
                    except Exception:
                        pass

        threading.Thread(target=_loop, daemon=True).start()

    def _click_finished(self, err):
        self.btn_start.config(state='normal')
        self.btn_stop.config(state='disabled')
        if err:
            self.sv_status.set(f"⚠️ {err}")
            self.sv_progress.set("")
        else:
            self.sv_status.set("✅ 点击完成")
            self.sv_progress.set("")

    def _stop_click(self):
        self.engine.stop()
        self.sv_status.set("✅ 已停止点击")

    def _toggle_click(self):
        if self.engine.running:
            self._stop_click()
        else:
            self._start_click()

    def _toggle_recording(self):
        if self.recorder.recording:
            self._stop_rec()
        else:
            self._start_rec()

    def _toggle_playback(self):
        if self.recorder.playing:
            self._stop_play_rec()
        else:
            self._play_rec()

    def _toggle_flow(self):
        if self.flow_engine.running:
            self._stop_flow()
        else:
            self._run_flow()

    def _emergency_stop(self):
        """紧急停止所有操作"""
        self.engine.stop()
        self.flow_engine.stop()
        self.recorder.stop_recording()
        self.recorder.stop_playback()
        self.btn_start.config(state='normal')
        self.btn_stop.config(state='disabled')
        self.btn_rec_start.config(state='normal')
        self.btn_rec_stop.config(state='disabled')
        self.btn_play.config(state='normal')
        self.btn_stop_play.config(state='disabled')
        self.btn_stop_flow.config(state='disabled')
        self.sv_status.set("🛑 紧急停止：所有操作已终止")
        self.sv_progress.set("")
        self.sv_flow_progress.set("")

    # ════════════════ 录制逻辑 ════════════════

    def _start_rec(self):
        self.btn_rec_start.config(state='disabled')
        self.btn_rec_stop.config(state='normal')
        cur_vrect = _get_virtual_screen_rect()
        cur_w, cur_h = cur_vrect[2], cur_vrect[3]
        self.sv_rec_status.set(f"🔴 录制中… ({cur_w}×{cur_h})")
        for item in self.tree_events.get_children():
            self.tree_events.delete(item)

        def on_event(action, ev):
            if action == 'add':
                self.root.after(0, lambda: self._add_event_row(ev))
            elif action == 'remove_last':
                self.root.after(0, self._remove_last_event_row)

        self.recorder.start_recording(
            on_event,
            record_mouse=self.var_rec_mouse.get(),
            record_key=self.var_rec_key.get(),
            record_drag=self.var_rec_drag.get(),
            record_move=self.var_rec_move.get(),
        )

    def _draw_radius_circle(self, canvas, radius):
        """在 Canvas 上绘制容错范围圆圈"""
        canvas.delete('all')
        # 优先使用 winfo_width，若为 1（未渲染）则用 cget 获取配置宽度
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w <= 1:
            w = int(canvas.cget('width'))
        if h <= 1:
            h = int(canvas.cget('height'))
        size = min(w, h)
        center = size // 2
        max_r = size // 2 - 4  # 留边距
        display_r = min(radius, max_r)
        if display_r > 0:
            canvas.create_oval(center - display_r, center - display_r,
                               center + display_r, center + display_r,
                               outline='#1976D2', width=2, fill='#E3F2FD')
            canvas.create_text(center, center, text=f'{radius}px',
                               font=('Consolas', 8), fill='#1976D2')
        else:
            canvas.create_text(center, center, text='0',
                               font=('Consolas', 8), fill='gray')

    def _on_radius_change(self, var, canvas):
        """容错范围变化时更新圆圈预览"""
        try:
            radius = var.get()
        except (tk.TclError, ValueError):
            radius = 0
        self._draw_radius_circle(canvas, radius)

    def _add_event_row(self, ev, delay=None):
        seq = len(self.tree_events.get_children()) + 1
        btn_cn = {'left': '左键', 'right': '右键',
                  'middle': '中键'}.get(ev.get('button', 'left'), '左键')
        ev_type = ev.get('type', 'click')
        if ev_type == 'drag':
            type_str = '拖动'
            pos_str = f"({ev['x0']}, {ev['y0']}) → ({ev['x1']}, {ev['y1']})"
            time_str = f"{ev['time']:.3f} ({ev.get('duration', 0):.3f}s)"
        elif ev_type == 'key':
            type_str = '按键'
            key_display = ev.get('key', '')
            mods = ev.get('mods', [])
            if mods:
                mod_short = [m.replace('Key.', '') for m in mods]
                key_display = '+'.join(mod_short + [key_display])
            pos_str = key_display
            time_str = f"{ev['time']:.3f}"
            btn_cn = '-'
        elif ev_type == 'move':
            type_str = '移动'
            pos_str = f"({ev['x']}, {ev['y']})"
            time_str = f"{ev['time']:.3f}"
            btn_cn = '-'
        else:
            type_str = '点击'
            pos_str = f"({ev['x']}, {ev['y']})"
            time_str = f"{ev['time']:.3f}"
        # 按住时长列：所有事件类型都显示实际值
        hold = ev.get('hold_duration', 0)
        hold_str = f"{hold:.3f}" if hold > 0 else '0.000'
        # 延迟列：从事件数据计算与上一个事件的时间差
        if delay is not None:
            delay_str = f"{delay:.3f}" if delay > 0 else '0.000'
        else:
            # 自动计算：当前事件时间 - 上一个事件时间
            children = self.tree_events.get_children()
            if children:
                prev_vals = self.tree_events.item(children[-1], 'values')
                prev_time_str = str(prev_vals[4]).split()[0]  # 去掉可能的 [按住...] 后缀
                try:
                    prev_time = float(prev_time_str)
                    calc_delay = round(ev['time'] - prev_time, 3)
                    delay_str = f"{calc_delay:.3f}" if calc_delay > 0 else '0.000'
                except (ValueError, IndexError):
                    delay_str = '0.000'
            else:
                delay_str = '0.000'
        # 事件样式标记
        tag = self._ev_type_tags.get(ev_type, 'click_row')
        self.tree_events.insert('', 'end', values=(
            seq, type_str, pos_str, btn_cn, time_str, hold_str, delay_str
        ), tags=(tag,))
        children = self.tree_events.get_children()
        if children:
            self.tree_events.see(children[-1])

    def _toggle_move_visibility(self):
        """切换移动事件的显示/隐藏"""
        self._refresh_event_list()

    def _refresh_event_list(self):
        """根据当前 _current_events 和 show_moves 设置刷新事件列表"""
        show = self.var_show_moves.get()
        for item in self.tree_events.get_children():
            self.tree_events.delete(item)
        if not hasattr(self, '_current_events') or not self._current_events:
            return

        # 先构建行数据列表
        rows = []  # (seq_display, ev, ev_type, type_str, pos_str, btn_cn, time_str, hold_str, delay_str, is_insert, insert_num)
        orig_seq = 0  # 原始事件计数器（跳过插入事件）
        for i, ev in enumerate(self._current_events, 1):
            is_insert = ev.get('_is_insert', False)
            if is_insert:
                seq_display = f"插入{ev.get('_insert_num', '?')}"
            else:
                orig_seq += 1
                seq_display = str(orig_seq)
            ev_type = ev.get('type', 'click')
            btn_cn = {'left': '左键', 'right': '右键',
                      'middle': '中键'}.get(ev.get('button', 'left'), '左键')
            if ev_type == 'drag':
                type_str = '拖动'
                pos_str = f"({ev['x0']}, {ev['y0']}) → ({ev['x1']}, {ev['y1']})"
                time_str = f"{ev['time']:.3f} ({ev.get('duration', 0):.3f}s)"
            elif ev_type == 'key':
                type_str = '按键'
                key_display = ev.get('key', '')
                mods = ev.get('mods', [])
                if mods:
                    mod_short = [m.replace('Key.', '') for m in mods]
                    key_display = '+'.join(mod_short + [key_display])
                pos_str = key_display
                time_str = f"{ev['time']:.3f}"
                btn_cn = '-'
            elif ev_type == 'move':
                type_str = '移动'
                pos_str = f"({ev['x']}, {ev['y']})"
                time_str = f"{ev['time']:.3f}"
                btn_cn = '-'
            else:
                type_str = '点击'
                pos_str = f"({ev['x']}, {ev['y']})"
                time_str = f"{ev['time']:.3f}"
            hold = ev.get('hold_duration', 0)
            hold_str = f"{hold:.3f}" if hold > 0 else '0.000'
            # 计算延迟
            if i > 1:
                prev_ev = self._current_events[i - 2]
                calc_delay = round(ev['time'] - prev_ev['time'], 3)
                delay_str = f"{calc_delay:.3f}" if calc_delay > 0 else '0.000'
            else:
                delay_str = '0.000'
            rows.append((seq_display, ev, ev_type, type_str, pos_str, btn_cn, time_str, hold_str, delay_str, is_insert, ev.get('_insert_num', 0)))

        # 分组：将连续的 move 事件合并
        i = 0
        while i < len(rows):
            row = rows[i]
            ev_type = row[2]
            if ev_type == 'move' and not show:
                # 跳过移动事件（不显示）
                i += 1
                continue
            if ev_type == 'move':
                # 收集连续的 move 事件
                move_start = i
                while i < len(rows) and rows[i][2] == 'move':
                    i += 1
                move_end = i  # exclusive
                # 创建折叠组
                first_ev = rows[move_start][1]
                last_ev = rows[move_end - 1][1]
                seq_start = rows[move_start][0]
                seq_end = rows[move_end - 1][0]
                group_label = f"{seq_start}-{seq_end}"
                pos_range = f"({first_ev['x']}, {first_ev['y']}) → ({last_ev['x']}, {last_ev['y']})"
                move_count = move_end - move_start
                time_range = f"{first_ev['time']:.3f}~{last_ev['time']:.3f}"
                hold_str = '0.000'
                delay_str = '0.000'
                # 插入父行（折叠的移动组）
                parent_id = self.tree_events.insert('', 'end', values=(
                    group_label, f'移动×{move_count}', pos_range, '-',
                    time_range, hold_str, delay_str
                ), tags=('move_group',), open=False)
                # 插入子行（各个移动事件）
                for j in range(move_start, move_end):
                    r = rows[j]
                    child_tag = ('inserted_row',) if r[9] else ('move_child',)
                    self.tree_events.insert(parent_id, 'end', values=(
                        r[0], r[3], r[4], r[6], r[7], r[8]
                    ), tags=child_tag)
            else:
                # 非移动事件：直接插入
                if row[9]:  # is_insert
                    tag = 'inserted_row'
                else:
                    tag = self._ev_type_tags.get(row[2], 'click_row')
                self.tree_events.insert('', 'end', values=(
                    row[0], row[3], row[4], row[5], row[6], row[7], row[8]
                ), tags=(tag,))
                i += 1

    def _remove_last_event_row(self):
        """移除录制列表中最后一个事件行（用于将 click 替换为 drag 时）"""
        children = self.tree_events.get_children()
        if children:
            self.tree_events.delete(children[-1])

    def _stop_rec(self):
        self.recorder.stop_recording()
        self.btn_rec_start.config(state='normal')
        self.btn_rec_stop.config(state='disabled')
        count = len(self.recorder.events)
        rec_w = getattr(self.recorder, '_rec_w', '?')
        rec_h = getattr(self.recorder, '_rec_h', '?')
        self.sv_rec_status.set(f"已录制 {count} 个事件 ({rec_w}×{rec_h})")
        self.sv_status.set(f"✅ 录制完成，共 {count} 个事件")
        self.var_save_name.set(f"录制_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        if getattr(self, '_insert_mode', False):
            # 插入模式：将新事件插入到标记位置之后
            self._insert_mode = False
            new_events = list(self.recorder.events)
            if new_events and hasattr(self, '_insert_idx'):
                insert_at = self._insert_idx - 1  # seq 号是 1-based，转为 0-based
                # 标记插入事件
                self._insert_counter += 1
                for ev in new_events:
                    ev['_is_insert'] = True
                    ev['_insert_num'] = self._insert_counter
                self._current_events[insert_at:insert_at] = new_events
                self._refresh_event_list()
                # 高亮插入的事件范围
                children = self.tree_events.get_children()
                if insert_at < len(children):
                    inserted_items = children[insert_at:insert_at + len(new_events)]
                    for item in inserted_items:
                        self.tree_events.selection_add(item)
                self.sv_status.set(f"✅ 已在位置 {self._insert_idx} 后插入 {len(new_events)} 个事件")
                self.btn_insert_rec.config(state='normal')
                return
        # 正常录制完成：同步到可编辑事件列表
        self._current_events = list(self.recorder.events)
        self._refresh_event_list()
        if self._current_events:
            self.btn_insert_rec.config(state='normal')

    def _start_insert_rec(self):
        """在选中的事件之后插入新录制的操作"""
        if not self._current_events:
            messagebox.showinfo("提示", "没有已加载的事件，请先录制或加载一个操作")
            return
        if self.recorder.recording or self.recorder.playing:
            messagebox.showinfo("提示", "正在录制或复现中，请先停止")
            return
        # 获取选中的位置
        sel = self.tree_events.selection()
        if sel:
            # 找到选中行在 _current_events 中的索引
            vals = list(self.tree_events.item(sel[0], 'values'))
            try:
                self._insert_idx = int(vals[0])  # 1-based seq 号
            except (ValueError, IndexError):
                self._insert_idx = len(self._current_events)
        else:
            # 没有选中则追加到末尾
            self._insert_idx = len(self._current_events)
        # 标记插入位置
        self._mark_insert_position(self._insert_idx)
        self._insert_mode = True
        # 开始录制
        self.btn_rec_start.config(state='disabled')
        self.btn_rec_stop.config(state='normal')
        self.btn_insert_rec.config(state='disabled')
        self.sv_rec_status.set("插入录制中...")
        self.sv_status.set(f"🔄 在位置 {self._insert_idx + 1} 之后插入录制中...")

        def on_event(action, ev):
            if action == 'add':
                self.root.after(0, lambda: self._add_event_row(ev))
            elif action == 'remove_last':
                self.root.after(0, self._remove_last_event_row)

        self.recorder.start_recording(
            on_event,
            record_mouse=self.var_rec_mouse.get(),
            record_key=self.var_rec_key.get(),
            record_drag=self.var_rec_drag.get(),
            record_move=self.var_rec_move.get(),
        )

    def _mark_insert_position(self, idx_1based):
        """在事件列表中标记插入位置（黄色高亮行）"""
        # 清除旧标记
        for item in self.tree_events.get_children():
            tags = self.tree_events.item(item, 'tags')
            if 'insert_marker' in tags:
                self.tree_events.item(item, tags=())
        # 标记目标位置
        children = self.tree_events.get_children()
        if idx_1based <= len(children) and idx_1based > 0:
            target = children[idx_1based - 1]
            # 获取当前标签并追加 insert_marker
            cur_tags = list(self.tree_events.item(target, 'tags'))
            if 'insert_marker' not in cur_tags:
                cur_tags.append('insert_marker')
            self.tree_events.item(target, tags=tuple(cur_tags))
            self.tree_events.see(target)
        elif idx_1based == len(children) and children:
            # 追加到末尾时，标记最后一行
            target = children[-1]
            cur_tags = list(self.tree_events.item(target, 'tags'))
            if 'insert_marker' not in cur_tags:
                cur_tags.append('insert_marker')
            self.tree_events.item(target, tags=tuple(cur_tags))
            self.tree_events.see(target)

    # ════════════════ 复现逻辑 ════════════════

    def _play_rec(self):
        events = self.recorder.events
        if not events:
            messagebox.showinfo("提示", "没有可复现的事件，请先录制")
            return
        self.btn_play.config(state='disabled')
        self.btn_stop_play.config(state='normal')
        self.sv_status.set("🔄 复现中…")

        def on_progress(i, total):
            self.sv_play_progress.set(f"复现进度: {i}/{total}")

        def on_done(err):
            self.root.after(0, lambda: self._play_finished(err))

        self.recorder.play(events=events, speed=self.var_play_speed.get(),
                          loop=self.var_loop.get(), on_progress=on_progress, on_done=on_done,
                          rec_resolution=(self.recorder._rec_w, self.recorder._rec_h),
                          radius=self.var_play_radius.get())

    def _play_finished(self, err):
        self.btn_play.config(state='normal')
        self.btn_stop_play.config(state='disabled')
        self.sv_play_progress.set("")
        if err:
            self.sv_status.set(f"⚠️ {err}")
        else:
            self.sv_status.set("✅ 复现完成")

    def _stop_play_rec(self):
        self.recorder.stop_playback()
        self.sv_status.set("✅ 已停止复现")

    # ════════════════ 保存录制 ════════════════

    def _save_rec(self):
        if not self.recorder.events:
            messagebox.showinfo("提示", "没有可保存的事件")
            return
        name = self.var_save_name.get().strip()
        if not name:
            messagebox.showwarning("提示", "请输入保存名称")
            return
        path = self.recorder.save(name)
        if path:
            self.sv_status.set(f"✅ 已保存: {name}")
            self._refresh_list()
            messagebox.showinfo("保存成功", f"录制已保存到:\n{path}")
        else:
            messagebox.showerror("错误", "保存失败")

    # ════════════════ 录制管理 ════════════════

    def _refresh_list(self):
        for item in self.tree_files.get_children():
            self.tree_files.delete(item)
        self._recordings_cache = self.recorder.list_all()
        cur_vrect = _get_virtual_screen_rect()
        cur_w, cur_h = cur_vrect[2], cur_vrect[3]
        for rec in self._recordings_cache:
            created = (rec['created'][:19].replace('T', ' ')
                       if rec['created'] else '-')
            res = rec.get('resolution')
            if res and len(res) == 2:
                res_str = f"{res[0]}×{res[1]}"
                if res[0] != cur_w or res[1] != cur_h:
                    res_str += " ⚠️"
            else:
                res_str = "未知"
            self.tree_files.insert('', 'end', iid=rec['path'],
                                   values=(rec['name'], rec['count'],
                                          f"{rec['duration']:.1f}", res_str, created))

    def _open_folder(self):
        os.startfile(str(self.recorder.rec_dir))

    def _get_selected_rec(self):
        sel = self.tree_files.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一条录制")
            return None
        path = sel[0]
        for rec in self._recordings_cache:
            if rec['path'] == path:
                return rec
        return None

    def _load_recording_only(self):
        """加载已录制文件的步骤到操作录制事件列表（不自动复现）"""
        rec = self._get_selected_rec()
        if not rec:
            return
        if self.recorder.playing:
            messagebox.showinfo("提示", "正在复现中，请先停止")
            return
        events = rec['events']
        self._current_events = list(events)
        self._refresh_event_list()
        # 切换到操作录制标签
        self.nb.select(1)
        self.sv_rec_status.set(f"已加载: {rec['name']} ({len(events)} 步)")
        self.sv_status.set(f"已加载录制: {rec['name']}")
        if events:
            self.btn_insert_rec.config(state='normal')

    def _load_and_play(self):
        rec = self._get_selected_rec()
        if not rec:
            return
        if self.recorder.playing:
            messagebox.showinfo("提示", "正在复现中，请先停止")
            return

        events = rec['events']
        for item in self.tree_events.get_children():
            self.tree_events.delete(item)
        for i, ev in enumerate(events, 1):
            ev_type = ev.get('type', 'click')
            btn_cn = {'left': '左键', 'right': '右键',
                      'middle': '中键'}.get(ev.get('button', 'left'), '左键')
            if ev_type == 'drag':
                type_str = '拖动'
                pos_str = f"({ev['x0']}, {ev['y0']}) → ({ev['x1']}, {ev['y1']})"
                time_str = f"{ev['time']:.3f} ({ev.get('duration', 0):.3f}s)"
            elif ev_type == 'key':
                type_str = '按键'
                pos_str = '-'
                time_str = f"{ev['time']:.3f}"
                btn_cn = '-'
            elif ev_type == 'move':
                type_str = '移动'
                pos_str = f"({ev['x']}, {ev['y']})"
                time_str = f"{ev['time']:.3f}"
                btn_cn = '-'
            else:
                type_str = '点击'
                pos_str = f"({ev['x']}, {ev['y']})"
                time_str = f"{ev['time']:.3f}"
            hold = ev.get('hold_duration', 0)
            hold_str = f"{hold:.3f}" if hold > 0 else '0.000'
            # 计算与上一个事件的延迟
            if i > 1:
                prev_ev = events[i - 2]  # events 是 0-based, i 是 1-based
                calc_delay = round(ev['time'] - prev_ev['time'], 3)
                delay_str = f"{calc_delay:.3f}" if calc_delay > 0 else '0.000'
            else:
                delay_str = '0.000'
            tag = self._ev_type_tags.get(ev_type, 'click_row')
            self.tree_events.insert('', 'end', values=(
                i, type_str, pos_str, btn_cn,
                time_str, hold_str, delay_str
            ), tags=(tag,))
        # 同步到可编辑事件列表
        self._current_events = list(events)

        self.btn_play.config(state='disabled')
        self.btn_stop_play.config(state='normal')
        self.sv_status.set(f"🔄 复现: {rec['name']}")

        def on_progress(i, total):
            self.sv_play_progress.set(f"复现进度: {i}/{total}")

        def on_done(err):
            self.root.after(0, lambda: self._play_finished(err))

        rec_res = rec.get('resolution')
        self.recorder.play(events=self._current_events, speed=self.var_play_speed.get(),
                          loop=self.var_loop.get(), on_progress=on_progress, on_done=on_done,
                          rec_resolution=tuple(rec_res) if rec_res else None,
                          radius=self.var_play_radius.get())
        cur_w, cur_h = pyautogui.size().width, pyautogui.size().height
        if rec_res and (rec_res[0] != cur_w or rec_res[1] != cur_h):
            self.sv_status.set(f"🔄 复现: {rec['name']} (自动缩放 {rec_res[0]}×{rec_res[1]} → {cur_w}×{cur_h})")
        else:
            self.sv_status.set(f"🔄 复现: {rec['name']}")

    def _rename_file(self):
        rec = self._get_selected_rec()
        if not rec:
            return
        new_name = simpledialog.askstring("重命名", "输入新名称:",
                                          initialvalue=rec['name'], parent=self.root)
        if new_name and new_name.strip():
            result = self.recorder.rename(rec['path'], new_name.strip())
            if result:
                self.sv_status.set(f"✅ 已重命名为: {new_name.strip()}")
                self._refresh_list()
            else:
                messagebox.showwarning("错误", "重命名失败（名称可能已存在）")

    def _delete_file(self):
        rec = self._get_selected_rec()
        if not rec:
            return
        if messagebox.askyesno("确认删除", f"确定要删除录制「{rec['name']}」吗？"):
            if self.recorder.delete(rec['path']):
                self.sv_status.set(f"✅ 已删除: {rec['name']}")
                self._refresh_list()
            else:
                messagebox.showerror("错误", "删除失败")

    # ════════════════ 全局快捷键 ════════════════

    _DEFAULT_HOTKEYS = {
        'start_stop':     'F6',
        'cancel':         'Escape',
        'start_stop_rec': 'F7',
        'start_stop_play':'F8',
        'start_stop_flow':'F9',
        'save_rec':       'F10',
        'emergency_stop': 'F11',
    }
    _HOTKEY_LABELS = {
        'start_stop':      '开始/停止点击',
        'cancel':          '取消取点',
        'start_stop_rec':  '开始/停止录制',
        'start_stop_play': '开始/停止复现',
        'start_stop_flow': '开始/停止流程',
        'save_rec':        '保存录制',
        'emergency_stop':  '紧急停止全部',
    }
    _KEY_MAP = {
        'F1': pynput_keyboard.Key.f1,
        'F2': pynput_keyboard.Key.f2,
        'F3': pynput_keyboard.Key.f3,
        'F4': pynput_keyboard.Key.f4,
        'F5': pynput_keyboard.Key.f5,
        'F6': pynput_keyboard.Key.f6,
        'F7': pynput_keyboard.Key.f7,
        'F8': pynput_keyboard.Key.f8,
        'F9': pynput_keyboard.Key.f9,
        'F10': pynput_keyboard.Key.f10,
        'F11': pynput_keyboard.Key.f11,
        'F12': pynput_keyboard.Key.f12,
        'Escape': pynput_keyboard.Key.esc,
        'Insert': pynput_keyboard.Key.insert,
        'Delete': pynput_keyboard.Key.delete,
        'Home': pynput_keyboard.Key.home,
        'End': pynput_keyboard.Key.end,
        'PageUp': pynput_keyboard.Key.page_up,
        'PageDown': pynput_keyboard.Key.page_down,
        'Tab': pynput_keyboard.Key.tab,
        'Space': pynput_keyboard.Key.space,
        'Pause': pynput_keyboard.Key.pause,
    }
    # 动态添加字母键和数字键
    for _ch in 'abcdefghijklmnopqrstuvwxyz':
        _KEY_MAP[_ch.upper()] = _ch
    for _d in '0123456789':
        _KEY_MAP[_d] = _d
    _KEY_OPTIONS = [
        'F1','F2','F3','F4','F5','F6','F7','F8','F9','F10','F11','F12',
        'Escape','Insert','Delete','Home','End','PageUp','PageDown','Space','Pause',
    ] + [chr(c) for c in range(ord('A'), ord('Z')+1)] + [str(d) for d in range(10)]

    def _load_hotkeys(self):
        if self.hotkey_file.exists():
            try:
                with open(self.hotkey_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                merged = dict(self._DEFAULT_HOTKEYS)
                merged.update(data)
                return merged
            except Exception:
                pass
        return dict(self._DEFAULT_HOTKEYS)

    def _save_hotkeys(self):
        with open(self.hotkey_file, 'w', encoding='utf-8') as f:
            json.dump(self.hotkeys, f, ensure_ascii=False, indent=2)

    def _update_hotkey_hint(self):
        parts = []
        for action, label in self._HOTKEY_LABELS.items():
            key = self.hotkeys.get(action, self._DEFAULT_HOTKEYS.get(action, ''))
            # 缩短标签显示
            short = label.replace('开始/停止', '开关').replace('紧急停止全部', '紧急停止')
            parts.append(f"{key} {short}")
        self.sv_hotkey_hint.set("快捷键: " + " | ".join(parts) + " | 安全退出: 鼠标移至左上角")

    def _key_name_to_pynput(self, name):
        return self._KEY_MAP.get(name)

    def _start_kb_listener(self):
        key_map = {}
        for action in self._HOTKEY_LABELS:
            key_name = self.hotkeys.get(action, self._DEFAULT_HOTKEYS.get(action))
            if key_name:
                pynput_key = self._key_name_to_pynput(key_name)
                if pynput_key:
                    key_map[pynput_key] = action

        def on_press(key):
            try:
                action = key_map.get(key)
                if action == 'start_stop':
                    self.root.after(0, self._toggle_click)
                elif action == 'cancel':
                    self.root.after(0, self._cancel_pick)
                elif action == 'start_stop_rec':
                    self.root.after(0, self._toggle_recording)
                elif action == 'start_stop_play':
                    self.root.after(0, self._toggle_playback)
                elif action == 'start_stop_flow':
                    self.root.after(0, self._toggle_flow)
                elif action == 'save_rec':
                    self.root.after(0, self._save_rec)
                elif action == 'emergency_stop':
                    self.root.after(0, self._emergency_stop)
            except Exception:
                pass

        self._kb_l = pynput_keyboard.Listener(on_press=on_press)
        self._kb_l.start()

    def _restart_kb_listener(self):
        if self._kb_l:
            self._kb_l.stop()
        self._start_kb_listener()

    # ──────── Tab 5: 快捷键设置 ────────
    def _build_hotkey_tab(self, parent):
        parent.columnconfigure(0, weight=1)

        # 说明
        ttk.Label(
            parent,
            text="自定义全局快捷键（重启监听后生效，关闭窗口自动保存）",
            foreground='gray', font=('Microsoft YaHei UI', 9)
        ).grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 12))

        self._hotkey_combos = {}
        row = 1

        for action, label in self._HOTKEY_LABELS.items():
            ttk.Label(parent, text=label, font=('Microsoft YaHei UI', 10)
                     ).grid(row=row, column=0, sticky='e', padx=(0, 10), pady=6)

            current = self.hotkeys.get(action, self._DEFAULT_HOTKEYS[action])
            var = tk.StringVar(value=current)
            combo = ttk.Combobox(parent, textvariable=var,
                                values=self._KEY_OPTIONS, state='readonly',
                                width=14)
            combo.grid(row=row, column=1, sticky='w', pady=6)
            self._hotkey_combos[action] = var
            row += 1

        # 冲突提示
        self.sv_hotkey_conflict = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self.sv_hotkey_conflict,
                  foreground='red', font=('Microsoft YaHei UI', 9)
                 ).grid(row=row, column=0, columnspan=3, sticky='w', pady=4)
        row += 1

        # 按钮区
        bf = ttk.Frame(parent)
        bf.grid(row=row, column=0, columnspan=3, pady=16)

        ttk.Button(bf, text="✅ 应用并重启快捷键",
                   command=self._apply_hotkeys, width=22
                  ).pack(side='left', padx=8)
        ttk.Button(bf, text="🔄 恢复默认",
                   command=self._reset_hotkeys, width=16
                  ).pack(side='left', padx=8)

        # 当前绑定预览
        lf = ttk.LabelFrame(parent, text="当前绑定预览", padding=10)
        lf.grid(row=row+1, column=0, columnspan=3, sticky='ew', pady=(8, 0))
        self.sv_hotkey_preview = tk.StringVar()
        self._update_hotkey_preview()
        ttk.Label(lf, textvariable=self.sv_hotkey_preview,
                  font=('Consolas', 10)).pack(anchor='w')

    def _update_hotkey_preview(self):
        lines = []
        for action, label in self._HOTKEY_LABELS.items():
            key = self.hotkeys.get(action, self._DEFAULT_HOTKEYS[action])
            lines.append(f"  {label:16s} →  {key}")
        self.sv_hotkey_preview.set('\n'.join(lines))

    def _check_hotkey_conflict(self):
        used = {}
        for action, var in self._hotkey_combos.items():
            val = var.get()
            if val in used:
                return f"⚠️ 冲突：'{self._HOTKEY_LABELS[action]}' 和 '{self._HOTKEY_LABELS[used[val]]}' 使用了相同的快捷键 {val}"
            used[val] = action
        return None

    def _apply_hotkeys(self):
        conflict = self._check_hotkey_conflict()
        if conflict:
            self.sv_hotkey_conflict.set(conflict)
            return
        self.sv_hotkey_conflict.set("")

        for action, var in self._hotkey_combos.items():
            self.hotkeys[action] = var.get()
        self._save_hotkeys()
        self._restart_kb_listener()
        self._update_hotkey_hint()
        self._update_hotkey_preview()
        self.sv_status.set("✅ 快捷键已更新")

    def _reset_hotkeys(self):
        for action, default in self._DEFAULT_HOTKEYS.items():
            self.hotkeys[action] = default
            if action in self._hotkey_combos:
                self._hotkey_combos[action].set(default)
        self._save_hotkeys()
        self._restart_kb_listener()
        self._update_hotkey_hint()
        self._update_hotkey_preview()
        self.sv_hotkey_conflict.set("")
        self.sv_status.set("✅ 快捷键已恢复默认")

    # ════════════════ 鼠标位置追踪 ════════════════

    def _tick_pos(self):
        try:
            x, y = pyautogui.position()
            self.sv_pos.set(f"鼠标: ({x}, {y})")
        except Exception:
            pass
        self.root.after(200, self._tick_pos)

    # ════════════════ 退出 ════════════════

    def _quit(self):
        try:
            self.engine.stop()
            self.flow_engine.stop()
            self.recorder.stop_recording()
            self.recorder.stop_playback()
            if hasattr(self, '_pick_win') and self._pick_win:
                try:
                    self._pick_win.destroy()
                except Exception:
                    pass
            if self._kb_l:
                self._kb_l.stop()
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)


# ═══════════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    root = tk.Tk()
    # 使用 clam 主题以支持 Treeview 标签背景色
    style = ttk.Style(root)
    style.theme_use('clam')
    # 配置 Treeview 行高和基础样式
    style.configure('Treeview',
                     rowheight=24,
                     font=('Microsoft YaHei UI', 9),
                     background='white',
                     fieldbackground='white')
    style.map('Treeview', background=[('selected', '#0078D4')])
    app = AutoClickerApp(root)
    root.mainloop()
    sys.exit(0)

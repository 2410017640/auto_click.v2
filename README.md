# 连点器 Pro (Auto Clicker Pro)

高级屏幕点击自动化工具，支持单点点击、操作录制回放、可视化流程编辑。

## 功能一览

| 模块 | 功能 |
|------|------|
| **单点点击** | 坐标输入/屏幕取点，设置点击次数、间隔、速度，随机偏移半径 |
| **操作录制** | 录制鼠标+键盘操作，支持按住时长、延迟编辑、容错范围实时预览 |
| **录制管理** | 加载/重命名/删除录制文件，支持在已录制操作间插入新操作 |
| **高级模式** | 可视化流程编辑器，支持截图匹配、分支逻辑、循环跳转、拖拽排序 |
| **快捷键** | 7 个快捷键可自定义，支持 F6 启停、Esc 紧急取消 |

## 快速开始

### 方式一：直接运行 EXE（推荐）

1. 下载 `连点器Pro.exe`
2. 双击运行，无需安装 Python

### 方式二：从源码运行

```bash
pip install -r requirements.txt
python autoclicker_pro.py
```

### 方式三：打包为 EXE

```bash
pip install pyinstaller
pyinstaller autoclicker_pro.spec --noconfirm --clean
# 输出: dist/连点器Pro.exe
```

## 依赖

| 库 | 用途 |
|----|------|
| pyautogui | 鼠标/键盘自动化 |
| pynput | 全局键鼠监听 |
| Pillow | 图像处理 |
| opencv-python | 截图模板匹配 |
| numpy | 数组运算 |

## 快捷键

| 默认快捷键 | 功能 |
|-----------|------|
| F6 | 开始/停止 |
| Esc | 取消操作 |
| F1-F5 | 其他自定义动作 |

可在「快捷键设置」标签页中修改。

## 项目结构

```
autoclicker/
├── autoclicker_pro.py      # 主程序
├── autoclicker_pro.spec    # PyInstaller 打包配置
├── build.bat               # 一键打包脚本
├── requirements.txt        # Python 依赖
├── hotkey_settings.json    # 快捷键配置（运行时生成）
├── recordings/             # 录制文件目录
│   └── 录制_*.json
└── flows/                  # 流程文件目录（高级模式）
    └── *.json
```

## 安全退出

鼠标移至屏幕左上角可紧急中断运行中的操作。

## 许可

MIT License

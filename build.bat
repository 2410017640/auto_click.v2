@echo off
chcp 65001 >nul
echo ============================================
echo   连点器 Pro - 自动打包脚本
echo ============================================
echo.

:: 检查 PyInstaller
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [INFO] 正在安装 PyInstaller...
    pip install pyinstaller -q
)

:: 清理旧构建
echo [1/3] 清理旧构建文件...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

:: 打包
echo [2/3] 正在打包为 EXE（这可能需要几分钟）...
pyinstaller autoclicker_pro.spec --noconfirm --clean

if errorlevel 1 (
    echo.
    echo [ERROR] 打包失败！请检查错误信息。
    pause
    exit /b 1
)

:: 完成
echo.
echo [3/3] 打包完成！
echo.
echo 输出目录: dist\连点器Pro\
echo 可执行文件: dist\连点器Pro\连点器Pro.exe
echo.
echo 将 dist\连点器Pro 文件夹整体分发给用户即可使用。
echo.
pause

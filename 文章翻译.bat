@echo off
setlocal
cd /d "%~dp0"

REM 检查 Python 环境
if not exist "python_embed\python.exe" (
    echo [错误] 未找到 python_embed\python.exe 环境。
    pause
    exit /b 1
)

echo 正在启动 WebUI Prompt Helper...
"python_embed\python.exe" "subtitle\webui_gui.py"

REM 检查退出状态
if errorlevel 1 (
    echo [错误] 程序异常退出，错误代码: %ERRORLEVEL%
    pause
)

endlocal
exit /b 0

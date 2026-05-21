@echo off
setlocal
cd /d "%~dp0"

REM 检查 Python 环境
if not exist "python_embed\python.exe" (
    echo [错误] 未找到 python_embed\python.exe 环境。
    pause
    exit /b 1
)

REM 初始化变量
set "ENABLE_NAMES_DB=False"

REM 处理参数
if /i "%~1"=="/names" set "ENABLE_NAMES_DB=True"

REM 显示状态
if "%ENABLE_NAMES_DB%"=="True" (
    echo [信息] 已启用人名数据库。
) else (
    echo [信息] 人名数据库已禁用 (默认值)。使用 /names 参数可启用。
)

echo 正在启动 Subtitle Translator GUI...
"python_embed\python.exe" "subtitle\gui_app.py"

REM 检查退出状态
if errorlevel 1 (
    echo [错误] 程序异常退出，错误代码: %ERRORLEVEL%
    pause
)

endlocal
exit /b 0

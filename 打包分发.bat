@echo off
chcp 65001 >nul
if exist "%~dp0python_embed\python.exe" (
    "%~dp0python_embed\python.exe" "%~dp0distribute.py"
) else (
    python "%~dp0distribute.py"
)
pause
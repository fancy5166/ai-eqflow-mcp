@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
    python install.py %*
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        py install.py %*
    ) else (
        echo [X] 未检测到 Python。请先安装 Python 3.10+：https://www.python.org/downloads/
        echo     安装时务必勾选 "Add python.exe to PATH"
        pause
        exit /b 2
    )
)
echo.
pause

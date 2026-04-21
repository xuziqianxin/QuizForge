@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ===========================================
echo      题库管理与答题系统 - 启动器
echo ===========================================
echo.

:: 1. 检测 Python 环境
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python 环境！
    echo.
    echo 请安装 Python 3.7 或更高版本。
    echo 推荐下载地址：https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"。
    echo.
    pause
    exit /b 1
)

:: 获取 Python 版本信息
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [信息] 检测到 Python 版本：!PY_VER!

:: 检查版本是否 >= 3.7
for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
    set MAJOR=%%a
    set MINOR=%%b
)
if !MAJOR! lss 3 (
    echo [错误] Python 版本过低，需要 Python 3.7 或更高版本。
    pause
    exit /b 1
)
if !MAJOR! equ 3 if !MINOR! lss 7 (
    echo [错误] Python 版本过低，需要 Python 3.7 或更高版本。
    pause
    exit /b 1
)

echo [信息] Python 环境正常。
echo.

:: 2. 检查并安装必要依赖
echo [信息] 正在检查依赖库...
set NEED_INSTALL=0

:: 检查 beautifulsoup4
python -c "import bs4" >nul 2>nul
if %errorlevel% neq 0 (
    echo [警告] 缺少依赖库：beautifulsoup4
    set NEED_INSTALL=1
)

:: 检查 pypinyin（可选）
python -c "import pypinyin" >nul 2>nul
if %errorlevel% neq 0 (
    echo [提示] 可选依赖 pypinyin 未安装（中文文件名转拼音将使用备用方案）。
    echo 是否安装 pypinyin？安装后可获得更好的中文文件名处理。
    choice /c YN /n /m "安装 pypinyin？[Y/N] (默认 N): "
    if !errorlevel! equ 1 (
        set NEED_INSTALL=1
        set INSTALL_PYPINYIN=1
    )
)

if !NEED_INSTALL! equ 1 (
    echo.
    echo [信息] 正在安装所需依赖库...
    echo.
    
    :: 升级 pip（可选）
    python -m pip install --upgrade pip >nul 2>nul
    
    :: 安装 beautifulsoup4
    python -c "import bs4" >nul 2>nul
    if !errorlevel! neq 0 (
        echo 正在安装 beautifulsoup4...
        python -m pip install beautifulsoup4
        if !errorlevel! neq 0 (
            echo [错误] beautifulsoup4 安装失败，请手动执行：pip install beautifulsoup4
            pause
            exit /b 1
        )
    )
    
    :: 安装 pypinyin（如果用户选择安装）
    if defined INSTALL_PYPINYIN (
        echo 正在安装 pypinyin...
        python -m pip install pypinyin
        if !errorlevel! neq 0 (
            echo [警告] pypinyin 安装失败，程序仍可正常运行（中文文件名将使用备用方案）。
        )
    )
    
    echo.
    echo [信息] 依赖安装完成。
)

echo.
echo ===========================================
echo           启动题库管理程序
echo ===========================================
echo.

:: 3. 启动主程序
python quiz_manager.py

:: 若程序异常退出，暂停以便查看错误信息
if %errorlevel% neq 0 (
    echo.
    echo [错误] 程序运行异常，请检查上方错误信息。
    pause
) else (
    echo.
    echo 程序已正常退出。
    timeout /t 2 >nul
)

endlocal
exit /b 0
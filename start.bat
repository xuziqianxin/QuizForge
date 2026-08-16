@echo off
setlocal EnableExtensions
title QuizForge - Terminal Quiz System
cd /d "%~dp0"

REM -- normalize PYTHON_HOME (strip trailing backslash) --
if defined PYTHON_HOME (
    if "%PYTHON_HOME:~-1%"=="\" set "PYTHON_HOME=%PYTHON_HOME:~0,-1%"
)

echo ==========================================
echo   QuizForge - Terminal Quiz System
echo ==========================================
echo.

set "PYEXE="

REM ---------------------------------------------------------------
REM Find a usable Python interpreter. Probe in order and prefer one
REM that already has the required packages (textual etc.):
REM   1) py launcher (Python 3)
REM   2) python on PATH
REM   3) interpreter pointed to by PYTHON_HOME
REM ---------------------------------------------------------------

REM -- Candidate 1: py launcher --
py -3 -c "import textual, requests, bs4, qrcode, Crypto" >nul 2>nul
if not errorlevel 1 set "PYEXE=py -3"

REM -- Candidate 2: python on PATH --
if not defined PYEXE (
    python -c "import textual, requests, bs4, qrcode, Crypto" >nul 2>nul
    if not errorlevel 1 set "PYEXE=python"
)

REM -- Candidate 3: PYTHON_HOME --
if not defined PYEXE (
    if defined PYTHON_HOME (
        if exist "%PYTHON_HOME%\python.exe" (
            "%PYTHON_HOME%\python.exe" -c "import textual, requests, bs4, qrcode, Crypto" >nul 2>nul
            if not errorlevel 1 set "PYEXE="%PYTHON_HOME%\python.exe""
        )
    )
)

REM -- Fallback: any Python, then auto-install dependencies --
if not defined PYEXE (
    py -3 -c "pass" >nul 2>nul
    if not errorlevel 1 set "PYEXE=py -3"
)
if not defined PYEXE (
    python -c "pass" >nul 2>nul
    if not errorlevel 1 set "PYEXE=python"
)
if not defined PYEXE (
    if defined PYTHON_HOME (
        if exist "%PYTHON_HOME%\python.exe" set "PYEXE="%PYTHON_HOME%\python.exe""
    )
)

if not defined PYEXE (
    echo [ERROR] No usable Python interpreter found.
    echo Please install Python 3.10+ and try again, or run manually:
    echo     pip install -r requirements.txt ^&^& python main.py
    pause
    exit /b 1
)

REM -- Dependency check (auto-install on first run) --
%PYEXE% -c "import textual, requests, bs4, qrcode, Crypto" >nul 2>nul
if errorlevel 1 (
    echo First run: installing dependencies - textual requests beautifulsoup4 qrcode
    %PYEXE% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed. Please check your network.
        pause
        exit /b 1
    )
)

echo Using interpreter: %PYEXE%
echo Hint: run in a Unicode-capable terminal - e.g. Windows Terminal.
echo       Press Ctrl+Q inside the app to quit.
echo.
%PYEXE% main.py
if errorlevel 1 (
    echo.
    echo The program exited with an error. See the messages above.
    pause
)
endlocal
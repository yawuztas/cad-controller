@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
if exist "%~dp0venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" "%~dp0cloudecad.py" %*
) else (
    python "%~dp0cloudecad.py" %*
)
if %ERRORLEVEL% neq 0 pause

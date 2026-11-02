@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
title CloudeCAD v3.0 - Saha Indirim (Healer Zinciri)

echo ==============================================================
echo   CloudeCAD v3.0 - SAHA INDIRIM (Okuma>Triyaj>Onarim>Optimize)
echo   Cikti: jobs\JOB-2026-S19-SAHA-01
echo ==============================================================
"%~dp0venv\Scripts\python.exe" "%~dp0tools\field_run_healer.py"
pause

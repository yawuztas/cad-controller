@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
title CloudeCAD v3.0 - Onay Istasyonu

echo ==============================================================
echo   CloudeCAD v3.0 - ONAY ISTASYONU baslatiliyor...
echo   Adres: http://127.0.0.1:8765
echo   Kapatmak icin bu pencerede CTRL+C ya da pencereyi kapatin.
echo ==============================================================
start "" http://127.0.0.1:8765
"%~dp0venv\Scripts\python.exe" "%~dp0tools\review_station.py" --job "%~dp0jobs\JOB-2026-S19-SAHA-01" --port 8765
pause

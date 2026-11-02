@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
title CloudeCAD - Otomatik Proje Denetim Servisi

echo ==============================================================================
echo    CloudeCAD — DWG / DXF Otomatik Proje İnceleme ve Rapor Üretici
echo ==============================================================================
echo.
echo  [1] Mevcut Projeleri İncele (Bir Kez Çalıştır)
echo  [2] Sürekli İzleme Modu (Watch Mode - Klasöre proje atıldıkça otomatik incele)
echo.
set /p SECIM="Lütfen bir mod seçin (1 veya 2) [Varsayılan: 2]: "
if "%SECIM%"=="" set SECIM=2

if "%SECIM%"=="1" (
    "%~dp0venv\Scripts\python.exe" "%~dp0batch_inspector.py"
) else (
    "%~dp0venv\Scripts\python.exe" "%~dp0batch_inspector.py" --watch
)

if %ERRORLEVEL% neq 0 pause

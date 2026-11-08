@echo off
chcp 65001 >nul
title CloudeCAD — 4 Kademeli Hesap ve Onarım Motoru
echo ========================================================
echo   CloudeCAD Hesap Motoru Baslatiliyor...
echo   Girdi:    01_girdi\
echo   Mevzuat:  02_mevzuat_ve_formuller\
echo   Motor:    03_hesap_motoru\
echo   Cikti:    04_cikti\
echo ========================================================
echo.
cd /d "%~dp0"
call .\venv\Scripts\activate.bat
python "03_hesap_motoru\calistir.py"
echo.
echo ========================================================
echo   Tamamlandi! Sonuclar '04_cikti' klasorundedir.
echo ========================================================
pause

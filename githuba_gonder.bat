@echo off
chcp 65001 >nul
title CloudeCAD — GitHub Senkronizasyonu
echo ========================================================
echo   CloudeCAD v3.0 -> GitHub (cad-controller) Gonderiliyor
echo ========================================================
echo.
cd /d "D:\autocad projesi"
git push -u origin main
echo.
echo ========================================================
echo   Islem tamamlandi!
echo ========================================================
pause

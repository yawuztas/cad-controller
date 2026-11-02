@echo off
chcp 65001 >nul
echo ============================================================
echo   CloudeCAD — Kurulum Betiği
echo ============================================================
echo.

:: Python kontrolü
python --version 2>nul
if errorlevel 1 (
    echo HATA: Python bulunamadı.
    echo Python 3.9+ indirin: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo.
echo [1/4] Bağımlılıklar kuruluyor...
pip install ezdxf shapely networkx matplotlib click colorlog xlrd openpyxl pywin32 --quiet
if errorlevel 1 (
    echo UYARI: Bazı paketler kurulamadı. Devam ediliyor...
)

echo.
echo [2/4] Çıktı dizini oluşturuluyor...
if not exist "outputs" mkdir outputs

echo.
echo [3/4] Test DXF oluşturuluyor...
python tests\create_test_dxf.py

echo.
echo [4/4] Birim testleri çalıştırılıyor...
set PYTHONUTF8=1
python tests\test_calculator.py
if errorlevel 1 (
    echo.
    echo UYARI: Bazı testler başarısız. Kurulum tamamlandı ama sorun var.
) else (
    echo Tüm testler başarılı!
)

echo.
echo ============================================================
echo   Kurulum Tamamlandı!
echo ============================================================
echo.
echo Kullanım:
echo   python main.py "dosya.dxf"
echo   python main.py "dosya.dxf" --rho 100
echo   python main.py "dosya.dxf" --verbose
echo.
echo DWG dosyaları için önce DXF'e dönüştürün:
echo   python setup_export_dxf.py "dosya.dwg"
echo.
echo Yardım için:
echo   python main.py --help
echo.
pause

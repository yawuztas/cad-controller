"""
CloudeCAD — Tier 0: DWG → DXF Dönüştürücü
==========================================
ODA File Converter (ücretsiz binary) kullanarak DWG dosyasını
DXF formatına dönüştürür. ezdxf DXF okuyabilir ama DWG okuyamaz.

ODA File Converter indirmek için:
  https://www.opendesign.com/guestfiles/oda_file_converter

Kurulum: Yukarıdaki linkten .exe veya .msi indirip kurun.
Varsayılan kurulum yolu: C:\\Program Files\\ODA\\ODAFileConverter\\
"""

import subprocess
import tempfile
import shutil
import logging
from pathlib import Path
from typing import Optional

from config import ODA_CONVERTER_PATHS

logger = logging.getLogger(__name__)


class ConversionError(Exception):
    """DWG→DXF dönüşüm hatası."""
    pass


def find_oda_converter() -> Optional[Path]:
    """ODA File Converter'ın yüklü olduğu yolu bulur."""
    for path in ODA_CONVERTER_PATHS:
        if path.exists():
            logger.debug(f"ODA Converter bulundu: {path}")
            return path
    # PATH'te de ara
    from_path = shutil.which("ODAFileConverter")
    if from_path:
        return Path(from_path)
    return None


def find_acad_core_console() -> Optional[Path]:
    """AutoCAD Core Console (accoreconsole.exe) yolunu dinamik olarak bulur."""
    # 1. Bilinen versiyon klasörleri (2030'dan 2020'ye kadar)
    for year in range(2030, 2019, -1):
        p = Path(rf"C:\Program Files\Autodesk\AutoCAD {year}\accoreconsole.exe")
        if p.exists():
            return p

    # 2. Autodesk klasörünü tara (Electrical ve özel sürümler dahil)
    autodesk_dir = Path(r"C:\Program Files\Autodesk")
    if autodesk_dir.exists():
        try:
            for sub in sorted(autodesk_dir.iterdir(), reverse=True):
                cand = sub / "accoreconsole.exe"
                if cand.exists():
                    return cand
        except Exception:
            pass

    # 3. Windows Registry (HKLM\SOFTWARE\Autodesk\AutoCAD)
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Autodesk\AutoCAD") as root_key:
            subkeys = []
            i = 0
            while True:
                try:
                    subkeys.append(winreg.EnumKey(root_key, i))
                    i += 1
                except OSError:
                    break
            for r_ver in sorted(subkeys, reverse=True):
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Autodesk\AutoCAD\{r_ver}") as r_key:
                        j = 0
                        while True:
                            try:
                                prod_key_name = winreg.EnumKey(r_key, j)
                                j += 1
                                try:
                                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Autodesk\AutoCAD\{r_ver}\{prod_key_name}") as prod_key:
                                        loc, _ = winreg.QueryValueEx(prod_key, "AcadLocation")
                                        cand = Path(loc) / "accoreconsole.exe"
                                        if cand.exists():
                                            return cand
                                except OSError:
                                    pass
                            except OSError:
                                break
                except OSError:
                    pass
    except Exception:
        pass

    # 4. PATH ortam değişkeninde ara
    which_path = shutil.which("accoreconsole.exe")
    if which_path:
        return Path(which_path)
    return None


def convert_dwg_via_accoreconsole(
    dwg_path: Path, output_dir: Path
) -> Path:
    """AutoCAD Core Console kullanarak DWG -> DXF çevrimi yapar."""
    console_exe = find_acad_core_console()
    if not console_exe:
        raise FileNotFoundError("accoreconsole.exe bulunamadı.")
    
    stem = dwg_path.stem.strip()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dxf_path = output_dir / f"{stem}.dxf"
    if dxf_path.exists():
        try:
            dxf_path.unlink()
        except Exception:
            pass

    # DWG başka bir AutoCAD oturumunda açıksa kilitlenmemesi için geçici izole kopyasını kullan
    temp_dir = Path(tempfile.mkdtemp(prefix="cad_conv_"))
    temp_dwg = temp_dir / "input.dwg"
    temp_dxf = temp_dir / "output.dxf"
    scr_path = temp_dir / "script.scr"

    try:
        shutil.copy2(dwg_path, temp_dwg)
        clean_temp_dxf = str(temp_dxf).replace("\\", "/")
        # Script adımları: FILEDIA kapalı, DXFOUT, QUIT ve onay için ayrı satırda Y
        script_cmds = [
            "FILEDIA 0",
            f'_DXFOUT "{clean_temp_dxf}" 16',
            "_QUIT",
            "_Y",
            "",
        ]
        scr_path.write_text("\n".join(script_cmds), encoding="utf-8")

        cmd = [str(console_exe), "/i", str(temp_dwg), "/s", str(scr_path)]
        logger.info(f"AutoCAD Core Console ile çevriliyor: {dwg_path.name}")
        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=60)

        if temp_dxf.exists() and temp_dxf.stat().st_size > 1000:
            shutil.copy2(temp_dxf, dxf_path)
            logger.info(f"✓ DXF başarıyla oluşturuldu: {dxf_path.name} ({dxf_path.stat().st_size:,} bytes)")
            return dxf_path
        else:
            raise ConversionError(f"AutoCAD Core Console DXF üretemedi. Çıktı: {res.stdout[:250]}")
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


def convert_dwg_via_autocad_com(dwg_path: Path, output_dir: Path) -> Path:
    """AutoCAD COM arayüzü ile DWG -> DXF çevrimi yapar."""
    import win32com.client
    import time
    
    stem = dwg_path.stem.strip()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dxf_path = output_dir / f"{stem}.dxf"
    if dxf_path.exists():
        try:
            dxf_path.unlink()
        except Exception:
            pass
            
    logger.info(f"AutoCAD COM Automation ile çevriliyor: {dwg_path.name}")
    acad = None
    try:
        acad = win32com.client.GetActiveObject("AutoCAD.Application")
    except Exception:
        acad = win32com.client.Dispatch("AutoCAD.Application")
        acad.Visible = False

    doc = acad.Documents.Open(str(dwg_path))
    time.sleep(2)
    clean_dxf_str = str(dxf_path).replace("\\", "/")
    doc.SendCommand(f'_DXFOUT "{clean_dxf_str}" 16 \n')
    time.sleep(2)
    doc.Close(False)

    if dxf_path.exists():
        logger.info(f"✓ DXF başarıyla oluşturuldu (COM): {dxf_path.name}")
        return dxf_path
    raise ConversionError("AutoCAD COM DXF üretemedi.")


def convert_dwg_to_dxf(
    dwg_path: Path,
    output_dir: Optional[Path] = None,
    dxf_version: str = "ACAD2018",
    audit: bool = True,
) -> Path:
    """
    DWG dosyasını DXF formatına dönüştürür.
    Önce yüklü AutoCAD Core Console'u (hızlı ve tam kayıpsız),
    sonra AutoCAD COM'u, bulunamazsa ODA File Converter'ı kullanır.
    """
    dwg_path = Path(dwg_path).resolve()
    if not dwg_path.exists():
        raise FileNotFoundError(f"DWG dosyası bulunamadı: {dwg_path}")

    out_target = output_dir if output_dir else dwg_path.parent

    # 1. Öncelik: AutoCAD Core Console
    if find_acad_core_console() is not None:
        try:
            return convert_dwg_via_accoreconsole(dwg_path, out_target)
        except Exception as e:
            logger.warning(f"AutoCAD Core Console çevrimi başarısız oldu ({e}), COM deneniyor...")

    # 2. Öncelik: AutoCAD COM Automation
    try:
        return convert_dwg_via_autocad_com(dwg_path, out_target)
    except Exception as e:
        logger.warning(f"AutoCAD COM çevrimi başarısız oldu ({e}), ODA deneniyor...")

    # 3. Öncelik: ODA File Converter
    converter = find_oda_converter()
    if converter is None:
        raise FileNotFoundError(
            "Ne AutoCAD Core Console ne de ODA File Converter bulunamadı.\n"
            "DWG dosyalarını doğrudan açabilmek için ODA File Converter kurabilir "
            "veya dosyayı AutoCAD ile DXF olarak kaydedebilirsiniz."
        )

    # Çıktı dizini
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="cloudecad_"))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ODA File Converter komut satırı:
    # ODAFileConverter <giriş_dizini> <çıktı_dizini> <hedef_format>
    #                  <hedef_versiyon> <audit> <recursive>
    # audit: 0=hayır, 1=evet
    # recursive: 0=hayır, 1=evet
    cmd = [
        str(converter),
        str(dwg_path.parent),   # Giriş dizini
        str(output_dir),        # Çıktı dizini
        "DXF",                  # Hedef format
        dxf_version,            # DXF versiyonu
        "1" if audit else "0",  # Audit
        "0",                    # Recursive (sadece belirtilen klasör)
    ]

    logger.info(f"ODA Converter çalıştırılıyor: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,        # 2 dakika timeout
        )
        if result.returncode != 0:
            raise ConversionError(
                f"ODA Converter başarısız (kod {result.returncode}):\n"
                f"{result.stderr}"
            )
    except subprocess.TimeoutExpired:
        raise ConversionError("ODA Converter zaman aşımına uğradı (120s).")
    except FileNotFoundError:
        raise FileNotFoundError(f"ODA Converter çalıştırılamadı: {converter}")

    # Üretilen DXF dosyasını bul
    dxf_name = dwg_path.stem + ".dxf"
    dxf_path = output_dir / dxf_name

    if not dxf_path.exists():
        # Büyük/küçük harf farkı olabilir
        candidates = list(output_dir.glob("*.dxf")) + list(output_dir.glob("*.DXF"))
        if candidates:
            dxf_path = candidates[0]
        else:
            raise ConversionError(
                f"ODA Converter çalıştı ama DXF dosyası üretilmedi.\n"
                f"Çıktı dizini: {output_dir}\n"
                f"ODA çıktısı: {result.stdout}"
            )

    logger.info(f"DWG→DXF dönüşümü tamamlandı: {dxf_path}")
    return dxf_path


def _get_central_dxf_cache_dir() -> Path:
    """Proje kök dizininde merkezi DXF önbellek klasörünü döner."""
    # D:\autocad projesi\.dxf_cache
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    cache_dir = root_dir / ".dxf_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def ensure_dxf(
    file_path: Path,
    output_dir: Optional[Path] = None,
    use_cache: bool = True
) -> Path:
    """
    Girdi dosyasına göre:
    - .dxf ise doğrudan döner
    - .dwg ise önce merkezi önbelleği (.dxf_cache) kontrol eder;
      dosya değişmemişse 0.005 saniyede önbellekten döner,
      yoksa DXF'e dönüştürüp önbelleğe kaydeder.
    """
    try:
        from common.dxf_converter import ensure_dxf as common_ensure_dxf
        return common_ensure_dxf(file_path, use_cache=use_cache)
    except Exception as ex:
        logger.debug(f"Ortak dönüştürücü çağrılamadı, yerel motor kullanılıyor: {ex}")

    file_path = Path(file_path).resolve()
    suffix = file_path.suffix.lower()

    if suffix == ".dxf":
        logger.info(f"DXF dosyası, dönüşüm gerekmez: {file_path.name}")
        return file_path
    elif suffix == ".dwg":
        if not file_path.exists():
            raise FileNotFoundError(f"DWG dosyası bulunamadı: {file_path}")

        if use_cache:
            try:
                stat = file_path.stat()
                cache_dir = _get_central_dxf_cache_dir()
                # Dosya adı + boyut + son değişiklik saniyesi ile deterministik anahtar
                cache_name = f"{file_path.stem}_{stat.st_size}_{int(stat.st_mtime)}.dxf"
                cached_dxf = cache_dir / cache_name
                if cached_dxf.exists() and cached_dxf.stat().st_size > 1000:
                    logger.info(f"⚡ DXF önbellekten hızlı okundu: {file_path.name}")
                    return cached_dxf
            except Exception as e:
                logger.debug(f"DXF önbellek kontrol hatası: {e}")

        logger.info(f"DWG dosyası, DXF'e dönüştürülüyor: {file_path.name}")
        target_dir = _get_central_dxf_cache_dir() if use_cache else output_dir
        converted_dxf = convert_dwg_to_dxf(file_path, output_dir=target_dir)

        if use_cache and converted_dxf.exists():
            try:
                stat = file_path.stat()
                cache_dir = _get_central_dxf_cache_dir()
                cache_name = f"{file_path.stem}_{stat.st_size}_{int(stat.st_mtime)}.dxf"
                cached_dxf = cache_dir / cache_name
                if converted_dxf.resolve() != cached_dxf.resolve():
                    shutil.copy2(converted_dxf, cached_dxf)
                    try:
                        converted_dxf.unlink()
                    except Exception:
                        pass
                return cached_dxf
            except Exception as e:
                logger.debug(f"DXF önbellek kayıt hatası: {e}")

        return converted_dxf
    else:
        raise ValueError(f"Desteklenmeyen dosya formatı: {suffix}. DWG veya DXF gerekli.")


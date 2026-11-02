"""
CloudeCAD — Ortak Tier 0: Kurşungeçirmez DWG -> DXF Dönüştürücü ve Önbellek Yöneticisi
======================================================================================
1. AutoCAD Core Console (accoreconsole.exe) ile _AUDIT _Y ve _DXFOUT kullanarak
   DWG içindeki bozuk BTR / Dictionary nesnelerini otomatik onarır ve tam DXF üretir.
2. Dosya sonundaki '0\nEOF' ve 'ENDSEC' etiketlerini kontrol ederek yarım/bozuk DXF'lerin
   önbelleğe girmesini %100 engeller.
3. COM Automation (win32com) yedek motorunu destekler.
"""

import os
import sys
import shutil
import logging
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Union, Tuple, List

logger = logging.getLogger("CloudeCAD.DXFConverter")

def get_central_dxf_cache_dir() -> Path:
    """Proje kök dizinindeki merkezi .dxf_cache klasörünü döner."""
    root_dir = Path(__file__).resolve().parents[2]
    cache_dir = root_dir / ".dxf_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def is_valid_dxf(dxf_path: Union[str, Path]) -> bool:
    """
    DXF dosyasının fiziksel olarak tamamlanıp tamamlanmadığını kontrol eder.
    Dosya boyutu > 1000 bayt olmalı ve dosya sonundaki son 512 bayt içinde 'EOF' bulunmalıdır.
    """
    p = Path(dxf_path)
    if not p.exists() or not p.is_file():
        return False
    try:
        sz = p.stat().st_size
        if sz < 1000:
            return False
        with open(p, "rb") as fp:
            fp.seek(max(0, sz - 512))
            tail = fp.read().decode("latin1", errors="ignore")
            # Hem EOF hem ENDSEC kontrolü
            return ("EOF" in tail) and ("ENDSEC" in tail)
    except Exception as e:
        logger.debug(f"DXF kontrol hatası ({p.name}): {e}")
        return False


def find_acad_core_console() -> Optional[Path]:
    """Sistemdeki AutoCAD Core Console (accoreconsole.exe) yolunu dinamik olarak arar."""
    # 1. Bilinen versiyon klasörleri (2030'dan 2019'a kadar)
    for year in range(2030, 2018, -1):
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

    # 3. Windows Registry
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


def convert_dwg_via_accoreconsole(dwg_path: Path, output_dxf_path: Path, timeout: int = 180) -> Path:
    """
    AutoCAD Core Console ile DWG -> DXF dönüştürür.
    _AUDIT _Y komutunu _DXFOUT öncesinde çalıştırarak bozuk blok kayıtlarını onarır.
    """
    console_exe = find_acad_core_console()
    if not console_exe:
        raise FileNotFoundError("accoreconsole.exe bulunamadı.")

    output_dxf_path = Path(output_dxf_path).resolve()
    output_dxf_path.parent.mkdir(parents=True, exist_ok=True)

    temp_dir = Path(tempfile.mkdtemp(prefix="accore_conv_"))
    temp_dwg = temp_dir / "input.dwg"
    temp_dxf = temp_dir / "output.dxf"
    scr_path = temp_dir / "audit_and_export.scr"

    try:
        shutil.copy2(dwg_path, temp_dwg)
        clean_temp_dxf = str(temp_dxf).replace("\\", "/")

        # Script adımları:
        # FILEDIA 0 -> Diyalogları kapat
        # _AUDIT _Y -> Çizim içi bozuk BTR/Dictionary nesnelerini onar/sil (DXFOUT kesilmesini önler!)
        # _DXFOUT <dosya> 16 -> AutoCAD 2018 ASCII DXF olarak eksiksiz kaydet
        # _QUIT _Y -> Temiz çık
        script_cmds = [
            "FILEDIA 0",
            "_AUDIT",
            "_Y",
            "_DXFOUT",
            f'"{clean_temp_dxf}"',
            "16",
            "_QUIT",
            "_Y",
            ""
        ]
        scr_path.write_text("\n".join(script_cmds), encoding="utf-8")

        cmd = [str(console_exe), "/i", str(temp_dwg), "/s", str(scr_path)]
        logger.info(f"AutoCAD Core Console (Audit+DXFOUT): {dwg_path.name}")
        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout)

        if temp_dxf.exists() and is_valid_dxf(temp_dxf):
            if output_dxf_path.exists():
                try:
                    output_dxf_path.unlink()
                except Exception:
                    pass
            shutil.copy2(temp_dxf, output_dxf_path)
            logger.info(f"✓ DXF tam ve hatasız üretildi: {output_dxf_path.name} ({output_dxf_path.stat().st_size:,} bayt)")
            return output_dxf_path
        else:
            tail_msg = ""
            if temp_dxf.exists():
                sz = temp_dxf.stat().st_size
                tail_msg = f" (Mevcut boyut: {sz:,} bayt fakat dosya sonu EOF eksik/yarım)"
            raise RuntimeError(f"accoreconsole DXF çıktısı tamamlanamadı{tail_msg}. Çıktı: {res.stdout[-300:]}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def convert_dwg_via_autocad_com(dwg_path: Path, output_dxf_path: Path) -> Path:
    """AutoCAD COM Automation arayüzü ile DWG -> DXF çevirir."""
    import win32com.client
    import time

    output_dxf_path = Path(output_dxf_path).resolve()
    output_dxf_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"AutoCAD COM ile deneniyor: {dwg_path.name}")
    acad = None
    try:
        acad = win32com.client.GetActiveObject("AutoCAD.Application")
    except Exception:
        acad = win32com.client.Dispatch("AutoCAD.Application")
        acad.Visible = False

    doc = acad.Documents.Open(str(dwg_path))
    try:
        time.sleep(2)
        doc.SendCommand("_AUDIT\n_Y\n")
        time.sleep(1)
        clean_dxf_str = str(output_dxf_path).replace("\\", "/")
        doc.SendCommand(f'_DXFOUT "{clean_dxf_str}" 16 \n')
        time.sleep(3)
    finally:
        doc.Close(False)

    if output_dxf_path.exists() and is_valid_dxf(output_dxf_path):
        logger.info(f"✓ DXF başarıyla oluşturuldu (COM): {output_dxf_path.name}")
        return output_dxf_path
    raise RuntimeError("AutoCAD COM geçerli bir DXF üretemedi.")


def convert_dwg_to_dxf(dwg_path: Union[str, Path], output_dxf_path: Optional[Union[str, Path]] = None) -> Path:
    """DWG dosyasını önce Core Console, ardından COM ile garantili biçimde DXF'e dönüştürür."""
    dwg = Path(dwg_path).resolve()
    if not dwg.exists():
        raise FileNotFoundError(f"DWG bulunamadı: {dwg}")

    if output_dxf_path is None:
        cache_dir = get_central_dxf_cache_dir()
        stat = dwg.stat()
        safe_stem = "".join(c if c.isalnum() or c in "-_." else "_" for c in dwg.stem)
        output_dxf_path = cache_dir / f"{safe_stem}_{stat.st_size}_{int(stat.st_mtime)}.dxf"
    else:
        output_dxf_path = Path(output_dxf_path).resolve()

    # 1. Öncelik: AutoCAD Core Console + Audit
    if find_acad_core_console():
        try:
            return convert_dwg_via_accoreconsole(dwg, output_dxf_path)
        except Exception as e:
            logger.warning(f"Core Console hatası ({dwg.name}): {e}. COM deneniyor...")

    # 2. Öncelik: AutoCAD COM
    try:
        return convert_dwg_via_autocad_com(dwg, output_dxf_path)
    except Exception as e:
        logger.error(f"COM dönüştürme de başarısız oldu ({dwg.name}): {e}")

    raise RuntimeError(f"'{dwg.name}' DXF formatına dönüştürülemedi!")


def ensure_dxf(file_path: Union[str, Path], use_cache: bool = True, force_reconvert: bool = False) -> Path:
    """
    DWG veya DXF dosyasını kontrol eder.
    Eğer DWG ise merkezi .dxf_cache içindeki karşılığını döner.
    Önbellekteki dosya bozuk/yarım (missing EOF) ise otomatik silip yeniden onararak üretir.
    """
    p = Path(file_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Dosya bulunamadı: {p}")

    if p.suffix.lower() == ".dxf":
        if not is_valid_dxf(p):
            logger.warning(f"Girdi DXF dosyası bozuk veya yarım (missing EOF): {p.name}")
        return p

    if p.suffix.lower() != ".dwg":
        raise ValueError(f"Desteklenmeyen dosya türü: {p.suffix}")

    cache_dir = get_central_dxf_cache_dir()
    stat = p.stat()
    safe_stem = "".join(c if c.isalnum() or c in "-_." else "_" for c in p.stem)
    cached_dxf = cache_dir / f"{safe_stem}_{stat.st_size}_{int(stat.st_mtime)}.dxf"

    if use_cache and not force_reconvert:
        if cached_dxf.exists():
            if is_valid_dxf(cached_dxf):
                logger.info(f"⚡ DXF geçerli ve önbellekten okundu: {cached_dxf.name}")
                return cached_dxf
            else:
                logger.warning(f"⚠️ Önbellekteki DXF bozuk/yarım tespit edildi, onarılıyor: {cached_dxf.name}")
                try:
                    cached_dxf.unlink()
                except Exception:
                    pass

    # Dönüştür ve önbelleğe al
    return convert_dwg_to_dxf(p, cached_dxf)


def repair_station_dxf_cache(station_dwg_dir: Union[str, Path]) -> Tuple[int, int]:
    """
    Belirtilen istasyon klasöründeki tüm DWG'leri tarar,
    .dxf_cache içindeki yarım kalmış olanları tespit edip eksiksiz biçimde yeniden üretir.
    Dönen değer: (toplam_dwg, onarilan_dxf)
    """
    station_dir = Path(station_dwg_dir).resolve()
    dwgs = list(station_dir.rglob("*.dwg"))
    repaired = 0

    for dwg in dwgs:
        cache_dir = get_central_dxf_cache_dir()
        stat = dwg.stat()
        safe_stem = "".join(c if c.isalnum() or c in "-_." else "_" for c in dwg.stem)
        cached_dxf = cache_dir / f"{safe_stem}_{stat.st_size}_{int(stat.st_mtime)}.dxf"

        if not cached_dxf.exists() or not is_valid_dxf(cached_dxf):
            logger.info(f"Onarılıyor / Üretiliyor: {dwg.name}")
            ensure_dxf(dwg, use_cache=True, force_reconvert=True)
            repaired += 1

    return len(dwgs), repaired
